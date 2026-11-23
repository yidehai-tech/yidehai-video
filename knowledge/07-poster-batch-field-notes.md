# 大字报批量出片实战经验（2026-11-23 真实踩坑沉淀）

> 来源：一次「批量生成10条大字报」的真实出片过程。前两轮全部失败或质量不合格（纯色背景 / 全批 FileNotFoundError），第三轮才达标。
> 适用场景：调用 `scripts/batch_runner.py` / `scripts/render_poster.py` 批量出大字报时，**出片前必读**。本文件补充 `06-rendering-playbook.md` 未覆盖的「大字报离线渲染层」坑。

---

## 一、环境层：`ffmpeg` / `ffprobe` 不在 PATH（Windows 必踩）

### 现象
`batch_runner.py` 首轮 10 条全 `failed`，错误栈末尾是 `FileNotFoundError: [WinError 2] 系统找不到指定的文件`，定位到 `render_poster_video()` 的 `subprocess.check_call(cmd)`。

### 根因
`render_poster.py` 与 `batch_runner.py` 内部**直接 subprocess 调用 `ffmpeg` / `ffprobe` 这两个裸命令**（第 447/506/513 行及 `ffprobe_duration()`），不带绝对路径。而系统 PATH 里通常没有它们——即使本机装了 OpenMotion / imageio-ffmpeg 也一样。

### 修复（出片前置动作）
1. 确认 `~/.yidehai-video/bin/` 下有 `ffmpeg.exe`。
2. **关键**：`ffprobe` 若是无扩展名的 bash shim（内容 `#!/usr/bin/env bash` + 调 `ffprobe_shim.py`），Windows 下 Python subprocess **无法直接执行无扩展名脚本**，会导致 `ffprobe_duration()` 抛 FileNotFoundError → 背景探测失败 → 全部回退纯色 `solid-fallback`。必须从本机 OpenMotion 缓存复制真正的 `ffprobe.exe` 到该目录：
   ```sh
   cp "<OM_HOME>/cache/native/win-x64/media-*/ffmpeg-*/bin/ffprobe.exe" ~/.yidehai-video/bin/ffprobe.exe
   ```
3. 每次批量出片命令前显式导出 PATH：
   ```sh
   export PATH="/c/Users/Administrator/.yidehai-video/bin:$PATH"
   python scripts/batch_runner.py ...
   ```
4. 自检：`ffprobe_duration(bg_full.mp4)` 能返回约 29.0 的浮点数即正常；若抛 FileNotFoundError，先别渲染。

---

## 二、素材层：单源视频切时间窗 = 视觉上"背景都一样"

### 现象
10 条成片技术上是 10 个不同时间窗、背景 10/10 去重，但用户审片后反馈"背景图片都一样"。核查发现：`forest_seg_a~g` 全是从**同一个 `bg_full.mp4`（同一片树林仰拍）**切出的片段——字节不同、画面几乎一样。

### 根因
`render_poster.py` 的 `pick_unique_bg_segment()` 按 `window_step = ceil(duration + 0.5)` ≈ 10 秒切窗。单个 29 秒视频只能出 3 个窗口；凑不够 N 条时会静默回退纯色，或（若手动切片段）退化为同片不同时间窗。**skill 的 `knowledge/media-catalog.json` 中 `bg_videos: []` 至今为空**，官方未内置任何风景空镜源；缺 Pexels/Pixabay Key 时无真实多样素材可用。

### 判定与修复
- **症结不在"是否视频"**：成片是 h264 视频流 + 文字层 overlay，背景真实在流动（抽首尾帧背景区像素差 > 20）。观感像图片是因为审片台 `review.html` 用静态封面 `cover-9x16.jpg` 做 video poster，且封面都截自同一片树林。
- **真正要做到背景不同，必须有真正不同的素材源**，不能靠切同一条视频：
  1. 配 Pexels 或 Pixabay 免费 Key（`config --set-pexels-key / --set-pixabay-key`）；
  2. 用 `media_manager.ensure_online_media('bg_videos', count=2, query=...)` 按**不同场景词**多次拉取（内置 `DEFAULT_SCENIC_QUERIES` 有 6 种：forest / mountain / ocean / flowers / leaves / meadow），每种拉 1–2 条，凑够 N 条不同场景；
  3. 拉新素材后**清空账本的 `used_bg_segments`**（`~/.yidehai-video/used_history.json`），否则旧窗口记录会干扰分配；
  4. 素材池要 ≥ N 个不重复窗口，否则超出的条目照样回退纯色。

### 铁律
> **单源视频切时间窗 ≠ 背景多样。** 用户要"每条背景不一样"时，先检查素材池里到底有几个**不同的视频文件/场景**，少于 N 就先补素材，绝不靠切片伪造多样性并向用户宣称"已去重"。

---

## 二·补：在线补素材实战（Pexels 限流 / 体积 / 隔离 / 强制指定）

配好 Pexels Key 按不同场景词补拉素材时，又踩了 4 个坑，一并记录：

1. **403 限流别误判成 Key 失效**：密集请求（6 分钟内连续拉十几条）会触发 Pexels 返回 403。等 20 秒后重试即可恢复；批量脚本里**每次查询间隔 ≥ 8 秒**，不要改成并发轰炸。
2. **默认 1080p 太慢**：`fetch_from_pexels` 默认挑接近 1080p 的 `video_files`（约 16MB/条），12 条要十几分钟且容易卡死在某个 URL。自己调 API 时改选**最小体积 / 720p** 的 file（3–5MB/条），下载快 3–5 倍。
3. **旧素材会混进新素材池**：缓存里原有的 `bg_full.mp4` / `forest_seg_*.mp4` 仍在素材池，随机抽中后又会回到雷同画面。把新拉的不同场景素材**单独复制到独立目录**（如 `cache/bg/pexels_pool/`），渲染时传 `--bg-dir` 指向它，从源头排除旧素材。
4. **`--bg` 补救残留重复**：即使素材池文件够多，`random.shuffle` 后仍可能出现"同一素材不同时间窗"（如 V001 向日葵 @0s、V006 向日葵 @10s）。找出未使用的素材，对那条单独 `render_poster.py --job ... --bg <未用素材> --force` 重渲；**注意 batch_runner 看到 mp4 已存在会跳过、不会自动更新 progress.json**，必须手动同步该条的 `bg` 字段并重新生成 `review.html`。

> 核验铁律补充：检查 `progress.json` 时要看 `bg` 字段里 `@` **前面的素材文件名是否 N 个互不相同**，而不是只看时间窗是否重复——同一文件的不同窗口在视觉上仍是"同一个背景"。

---

## 三、调度层：并发读账本竞态 + organize-by-date 破坏断点续跑

1. **批量渲染用 `workers=1`**：`workers=2` 时多个线程同时读写 `used_history.json`（读-挑-写非原子），会重复分配同一背景窗口，导致去重失效。串行虽慢但稳。
2. **批量出片别加 `--organize-by-date`**：它按运行时间戳新建 `outputs/YYYY-MM-DD/batch-HHMMSS/` 目录，重跑/断点续跑时进度写到新目录，旧目录的 `progress.json` 失效，已完成的条目会被重渲。**批量固定 `--out-dir`**（如 `outputs/大字报批量10条-YYYYMMDD/`）更可控。

---

## 四、交付层：审片台静态封面造成的"背景像图片"错觉

`batch_runner.py` 的 `write_review_html()` 用 `cover-9x16.jpg` 作为 `<video poster="...">`。封面是静帧，审片台未播放时显示的就是图片。若所有封面截自同一素材，用户极易误判"背景是图片/都一样"。
- 向用户交付时主动说明：成片背景为动态视频流，可点开播放确认；
- 封面与背景素材同源时，尽量让每条封面截自不同时间点/不同素材，减少误导。

---

## 五、交付前自检清单（大字报批量）

- [ ] 出片前 `export PATH` 含 `~/.yidehai-video/bin`，且该目录有真 `ffmpeg.exe` + `ffprobe.exe`；
- [ ] 素材池有 ≥ N 个**不同场景**视频（不是同一条切 N 段）；不足先配 Pexels/Pixabay Key 补素材，查询间隔 ≥ 8 秒防 403，优先下 720p 小文件加速；
- [ ] 新素材放独立目录并用 `--bg-dir` 指向，避免旧素材（bg_full / forest_seg_*）混入；
- [ ] 补素材后清空 `used_bg_segments` 账本再渲染；
- [ ] `workers=1` 串行、固定 `--out-dir`（不加 `--organize-by-date`）；
- [ ] 渲染后核对 `progress.json`：每条 `bg` 字段 `@` 前的**素材文件名是否真的 N 个互不相同**（不是只看时间窗）；有重复用 `--bg` 单独重渲并手动同步进度与审片台；
- [ ] 抽检首尾帧背景像素差 > 2（确认真视频在流动）；
- [ ] 抽检封面四段式排版无孤字、无裁切。
