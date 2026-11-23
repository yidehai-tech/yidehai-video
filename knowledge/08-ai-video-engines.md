# AI 视频生成、省点混剪与口播包装实操手册（即梦 CLI / Google Flow / 纯实拍 / MotionGit）

> 本手册覆盖除 `大字报` 与 `动效片` 之外的 4 条高拟真生产轨道。所有成片均严格遵守 `knowledge/01-brand-rules.md` 合规硬红线，**全片无品牌浮条、无全屏静态尾卡，话音一落利落收尾保完播**，并统一通过 **HeyGen HyperFrames**（`https://github.com/heygen-com/hyperframes`）完成高画质渲染与 `9:16` / `3:4` 双封面产出。

---

## 一、即梦 CLI（`dreamina`）—— 国内直连全自动生视频

**严格 Opt-in**：仅当成员明确要求「用即梦生视频 / 做条即梦片」时调用。

### 1. 前置自检与费用护栏
1. 运行 `python3 scripts/dreamina_runner.py check` 检查 CLI 可用性与当前积分余额（`user_credit`）；
2. 未登录时运行 `dreamina login`，将 OAuth 授权链接与 `user_code` 发给成员完成扫码并确认登录成功；
3. **不硬编码模型**：如成员指定特定模型，提交前先跑 `dreamina <subcommand> -h` 核对当前支持的参数组合（`model_version`、`duration`、`ratio`、`video_resolution`）；
4. **严禁静默重复提交**：统一通过 `scripts/dreamina_runner.py submit` 提交，脚本会把 `submit_id` 持久化到 `<task-dir>/dreamina_task.json`；超时或网络波动时只能用 `query` 续查旧 `submit_id`，绝不重发新任务扣双份积分。

### 2. 两种出片档位（推荐优先用「省积分混剪」）
- **档位 A：省积分混剪（推荐）**：
  - 用 `dreamina_runner.py submit --mode text2video --duration 5 --ratio 9:16 --video-resolution 720p --poll 60 --auto-download` 生成 1 段 **4–5 秒高吸睛开场镜头**（提示词强调写实中国居家场景、9:16 竖屏、无文字无水印）；
  - 再调用 `python3 scripts/media_manager.py footage --count 2` 从本机 `local_footage_dirs` 抽取 2 段未用过的真实实拍视频/图片；
  - 用 `scripts/package_ai_video.py --job job.json --out-dir outputs --organize-by-date`（`mode: "montage"` + `Edge-TTS` 干声旁白）一键合成 15–20 秒高留存成片。
- **档位 B：纯即梦全片**：
  - 直接生成 8–10 秒完整镜头（可按需用 `image2video` / `frames2video` / `multimodal2video`），下载后走 `package_ai_video.py`（`mode: "native_audio"` 或 `montage`）叠加顶标、防孤字大字幕、双封面与 8 帧质检图。

### 3. 常见报错处理
- **`AigcComplianceConfirmationRequired`**：提示成员先在即梦 Web 端使用该模型完成一次合规确认生成，再重试；
- **`ExceedConcurrencyLimit` (ret `1310`)**：立刻停止继续提交，用 `dreamina list_task` / `query` 跟进排队任务，或在成员预算允许下尝试一次对应 VIP 变体；
- **排队超过 1 小时**：保存 `submit_id` 汇报进度并结束当前轮次，后续直接用 `dreamina_runner.py query --task-dir <dir> --download` 取片。

---

## 二、Google Flow（`flow.google.com`）—— `ego-lite` 全自动生视频

**严格 Opt-in + 强前置 `ego-lite`**：仅当成员明确要求「用 Flow / Omni / Veo 生视频」时调用；开始前必须按 `knowledge/00-auto-setup.md` 第三节确认 `ego-browser` 已安装并输出 `ego-browser ready`。

### 1. 省点混合轮换策略（均耗 10–18 点/条）
1. **主力口播档（24–30 点）**：`Omni 1.2 Flash`（720p、9:16、原生中文口播，零乱码字幕/零水印）
   - **8s（24 点，高完播首选）**：口播台词 **40–45 个汉字**；
   - **10s（30 点，干货清单）**：口播台词 **52–58 个汉字**。
2. **省点混剪档（10 点）**：`Veo 3.1 - Lite`（720p、8s **无声模式**开场吸睛镜头）+ 2 段未用过的本地实拍（`media_manager.py footage`）+ `Edge-TTS` 干声旁白（15–20s）。
3. **0 点纯实拍档（0 点）**：3 段未用过的本地实拍视频/图片 + `Edge-TTS` 干声旁白（15–20s）。

> 注意：`Veo 3.1 - Fast`、`Veo 3.1 - Quality`、`Omni 1.1 Flash` 已/即将下线，不要选用。

### 2. `ego-browser` 实操防踩坑铁律
- **费用核对底线**：点击 `button[aria-label="开始生成"]` 前，必须先读页面 DOM 核对 `生成将消耗 X 个点数` 与预期一致（`24 / 30 / 10`），异常高价立刻中止并告知成员；完成后务必调用 `task.finish({ keep: [] })` 关闭 TaskSpace。
- **Omni 1.2 Flash（有声口播）**：
  1. 打开 `button[aria-label="设置"]`，确认 **`button[name="return-silent-videos"]` 为关闭（OFF）**；
  2. 模式选 **视频 + 竖屏（9:16）+ `Omni 1.2 Flash`（720p，严禁 360p）**；
  3. **时长滑块精确点击法**：`input[aria-label="时长"]` 范围 `0..12` 对应 `3s..15s`，**禁止点中心**（会重置到 4s）。先取 boundingBox `(x, y, w, h)`：
     - 目标 **8s**：`x + w * (5 / 12)`
     - 目标 **10s**：`x + w * (7 / 12)`
     点击后读 DOM 核实 `时长 8 秒 / 24 点`（或 `10 秒 / 30 点`）；
  4. Prompt 必须附带：`9:16 vertical smartphone UGC shot, realistic Chinese home background, natural daylight. No on-screen text, no subtitles, no watermarks, no logos.` + 引号包裹的完整中文口播台词。
- **Veo 3.1 - Lite（10 点无声开场）**：
  1. 打开设置面板，**务必打开 `button[name="return-silent-videos"]`（ON）**（避免触发「音频生成失败」）；
  2. 选 **`Veo 3.1 - Lite`**、竖屏 `9:16`、默认 8s，核对点数为 **10 点**。
- **提交与 720p 无损下载**：
  - 点击生成后等待 4–5 秒检查进度百分比（如 `7%`），**未确认状态前绝不盲目二次点击**；
  - 项目网格页出现 `img[alt="生成的视频缩略图"]` 且百分比消失即完成 → 点入详情页 → `button[aria-label="下载媒体内容"]` → 选 `720p` → 等待 `.mp4` 下载完成后移入任务目录；
  - 立刻运行 `python3 scripts/package_ai_video.py --job job.json --out-dir outputs --organize-by-date` 完成 HeyGen HyperFrames 渲染、8 帧质检与双封面产出。

---

## 三、0 点纯实拍混剪（`实拍混剪` / `montage`）

完全零 AI 点数消耗，适合高频日常出片或配合省点轮换：
1. 调用 `python3 scripts/media_manager.py footage --count 3` 从本机 `local_footage_dirs` 自动抽取 3 个**未在全局账本用过**的真实实拍视频或图片（静态图片在包装时会自动加上平滑 Ken Burns 轻推镜，绝不呆板）；
2. 写好合规旁白稿（80–110 字，15–20s）写入 `job.json`（`mode: "montage"`）；
3. 一键运行 `python3 scripts/package_ai_video.py --job job.json --out-dir outputs --organize-by-date`，自动完成 `Edge-TTS` 干声合成 → 片段拼接 → HeyGen HyperFrames 渲染（顶标 + 防孤字字幕 + 无浮条利落收尾）→ 8 帧 `qc-contact.jpg` → `9:16` & `3:4` 双封面 → 写入防重账本。

---

## 四、MotionGit 免费口播模板包装（`口播包装` / `motiongit`）

当成员手头已有**真人实拍口播视频**，想做成高质感综艺/杂志/海报风动效口播片时使用（如 MotionGit 官网免费模板「活力海报」「现代编辑」「纸张透视」等）：

1. **模板准备（零凭据隔离）**：
   - 本公开 Skill 仓库**不包含**任何个人 `.motion` 模板文件；
   - 成员从 MotionGit 官网自行下载免费 `.motion` 模板保存到本机目录（如 `~/Documents/motion-templates/`），并配置一次：
     `python3 scripts/media_manager.py config --set-motion-templates-dir "<本机模板目录>"`
2. **执行包装**：
   - 检测本机模板目录中的可用免费 `.motion` 模板，按成员指定的风格（或默认选用竖屏 9:16 模板）调用 MotionGit 官方 runtime，将真人实拍口播视频与合规字幕/关键词传入渲染；
   - **硬约束**：严格保留原始模板包与原素材不修改；严禁提取、打印或上传任何模板内凭据；渲染完成后同样做抽帧目视质检与 `9:16` / `3:4` 双封面补齐。

---

## 五、统一交付前质检清单（不可跳过）

任何轨道出片后，交付前必须查看 `qc-contact.jpg`、`cover-9x16.jpg`、`cover-3x4.jpg`，核验：
1. 画面无 AI 乱码字幕、无第三方平台水印、无畸形手/脸；
2. 顶标与字幕在安全区内、无单字孤行换行、无底部品牌浮条与静态全屏尾卡；
3. 双封面两行大字居中清晰、无边缘裁切；
4. 发布文案已标注按平台要求勾选「AI 生成」声明（纯实拍且未用 AI 配音的除外）。
