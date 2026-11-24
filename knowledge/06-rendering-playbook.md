# OpenMotion 出片实战手册（渲染组件 / 工程 / 质检）

> 适用时机：`knowledge/00-auto-setup.md` 已把 `@openmotion/app` 装好，**但真正导出 MP4 时卡住**。
> 这份手册沉淀自一次真实出片（10 秒 9:16 竖屏动效片）：安装只用了 1 分钟，导出能力却折腾了很久。
> 核心结论先记住三条：
> 1. **安装成功 ≠ 能导出**：还要 `browser` + `media` 两个 native 组件 `ready`，`capabilities.export === true`。
> 2. **别信"后台还在下载"**：后台 worker 会随会话结束被清理，先看进程是否活着，再谈速度。
> 3. **导出走前台同步渲染**：`openmotion_export_request` 的后台 worker 常被中断，用 `hyperframes render` 直接出片。

---

## 〇、路径与变量（不要写死）

一切以本机安装器输出为准，**不要照抄示例里的绝对路径或版本号**：

| 变量 | 怎么取 |
|---|---|
| `<OM_HOME>` | 安装时 `--home` 的值（Windows 通常 `%LOCALAPPDATA%\openmotion`；macOS 以安装器输出为准） |
| `<APP_ROOT>` | 读 `<OM_HOME>/install.json` 的 `appRoot` 字段 |
| `<LOCK>` | `<APP_ROOT>/scripts/runtime-lock.json`，含每个组件的 `url` 与 `sha256` |
| `<CACHE>` | `<OM_HOME>/cache/native/` |
| `<TARGET_KEY>` | 锁文件 `targets` 下的键：`win-x64` / `mac-arm64` |
| `<PROJECT_DIR>` | `<OM_HOME>/data/projects/<projectId>/` |

本次实测值仅作参照：app `0.2.1`、Node `22.22.2`（≥22.18 即可）、browser 为 chrome-headless-shell `156.0.8078.47`（126MB）、media 为 FFmpeg `9.0.2 essentials`（114.8MB）。

---

## 一、导出能力自检（出片前必做，30 秒）

```sh
node --input-type=module -e "
const m = await import('file:///<APP_ROOT>/scripts/npm-runtime.mjs');
console.log(JSON.stringify(await m.nativeRuntimeStatus('<APP_ROOT>')));
"
```

期望：
```json
{"components":[{"id":"browser","stage":"ready"},{"id":"media","stage":"ready"}],
 "capabilities":{"capture":true,"media":true,"export":true}}
```
`export: true` 才能导出 MP4。只要有一个不是 `ready`，走下面第二节，**不要先去建工程**（否则建好了也渲不出来）。

---

## 二、native 组件离线补齐（本次最大坑）

### 2.1 机制：sha256 缓存注入

`<APP_ROOT>/scripts/runtime-assets.mjs` 的 `download()` 会先算目标 zip 的 sha256，**一致就直接跳过下载去解压**。因此只要把校验正确的 zip 放进：

```
<CACHE>/downloads/<sha256>.zip
```

安装器就会跳过慢速下载。这是绕开网络问题最干净的办法，不需要改引擎源码。

### 2.2 先判断"下载中"是真是假

状态文件 `<CACHE>/<target_key>/*.status.json` 只是快照，**进程死了它不会自己变**。别看到 `downloading` 就一直等：

```sh
# 看状态里的 pid 是否还活着（Windows）
tasklist /FI "PID eq <pid>"
# macOS / Linux
ps -p <pid>
```
同时看 `<status.json>` 的 `updatedAt` 时间戳是否已停止增长、`<CACHE>/downloads/*.part` 大小是否还在变。
本次教训：状态停在 11:12、PID 已不存在，却误判成"速度慢还要 1 小时"，白等了一轮。

### 2.3 高速下载源（国内网络）

| 组件 | 官方源实测 | 可用替代 |
|---|---|---|
| browser | Google Storage 约 98KB/s | `https://cdn.npmmirror.com/binaries/chrome-for-testing/<version>/<platform>/<filename>.zip`（实测 5–85MB/s）。把官方 URL 中 `/chrome-for-testing-public/` 之后的路径拼到该前缀即可 |
| media | GitHub Releases 直接握手失败 | `https://gh-proxy.com/` 或 `https://ghfast.top/` + 完整 GitHub URL（约 240KB/s，支持标准 `206 Content-Range`） |

media 包大，先验证分段支持再并发：

```sh
curl -sS -I -L -r 10485760-10486800 "<代理URL>"   # 应返回 206 + Content-Range
```
支持就按 12 段并发拉、按序拼接、算 sha256。仓库内 `scripts/fetch_om_components.py` 已封装：
从 `<LOCK>` 动态读 url/sha256 → 优先镜像 → 分段并发 → 校验 → 落到 `<CACHE>/downloads/<sha256>.zip`。
**校验不通过的 zip 绝不能放进缓存**，否则引擎会解压出坏组件。

### 2.4 让引擎解压：`prepare`

```sh
node <APP_ROOT>/scripts/npm-installer.mjs prepare --home <OM_HOME>
```

### 2.5 已知故障：safe-delete 拦截导致 media 误标 failed

在部分会拦截删除操作的桌面 Agent 宿主（如 WorkBuddy 等）里，`prepare` 清理临时目录时可能被安全策略挡住，日志出现 `safe-delete`，media 被标成 `failed`——**但文件其实已完整解压**。先别重下，检查：

```
<CACHE>/<target_key>/media-XXXXXX/ffmpeg-*/bin/ffmpeg.exe
<CACHE>/<target_key>/media-XXXXXX/ffmpeg-*/bin/ffprobe.exe
```
两个都在就手动归位：

1. 把该临时目录重命名为 `media-<media 的 sha256>`；
2. 写 `<CACHE>/<target_key>/media-<sha256>.status.json`，内容 `{"pid":0,"stage":"ready","updatedAt":<当前毫秒时间戳>}`；
3. 清掉 `downloads/*.part` 与死 lock，删掉其余空的临时目录；
4. 跑一次 `ffmpeg.exe -version` / `ffprobe.exe -version` 确认可执行；
5. 再跑 `prepare` + 第一节自检，直到 `export: true`。

同理，渲染日志末尾的 `recordRenderSuccess ... safe-delete` 警告不影响成片（日志会明确 render already succeeded），抽帧确认即可。

---

## 三、建工程与渲染（绕开后台 worker）

### 3.1 原生 MCP 工具未热加载时：directAccess

按当前宿主替换 `<HOST>`（如 `workbuddy` / `claude` / `codex` / `cursor`）：
```sh
node <APP_ROOT>/scripts/npm-installer.mjs tools --home <OM_HOME> --host <HOST>
node <APP_ROOT>/scripts/npm-installer.mjs call <TOOL_NAME> --args-file <args.json> \
     --home <OM_HOME> --host <HOST>
```
`--args-file` 是 JSON；`call` 返回 MCP 的 `content[0].text`（通常还是一段 JSON，需要二次解析）。
常用：`openmotion_create_project` → `openmotion_edit_project` → `openmotion_get_project`。
工具调用可能触发宿主安全策略拦截 `reg.exe`，**只是警告，工具仍会正常返回，不要重试该程序**。

### 3.2 原生影片工程的 lint 硬要求

```sh
node <APP_ROOT>/scripts/lint-project.mjs <APP_ROOT> <PROJECT_DIR>
```
必须做到 `ok=true, errorCount=0, warningCount=0` 再渲染。本次踩到的四个：

1. **中文字体必须声明 `@font-face`**，`src: local("Microsoft YaHei")` 即可，不必打包字体文件；
2. **root composition 内不能有带嵌套的顶层 clip**，场景必须拆进 `data-composition-src` 指向的子合成文件（如 `compositions/film.html`）；
3. **同一元素不要叠两个 `fromTo`**，合并成单条 tween，否则动效互相打架；
4. `data-composition-variables` 里用到的变量都要声明。

工程形态：`index.html` 定 root（1080×1920 / 30fps / 10s），`compositions/film.html` 放四屏 SVG 插画 + GSAP 时间轴，`window.__timelines["film"] = tl`。

### 3.3 用前台同步渲染导出（推荐，别用 export_request）

`openmotion_export_request` 排队的后台 worker 会随 MCP 会话结束被清理，报 `EXPORT_WORKER_INTERRUPTED`。直接同步渲染：

```sh
export HYPERFRAMES_FFMPEG_PATH="<CACHE>/<target_key>/media-<sha>/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
export HYPERFRAMES_FFPROBE_PATH="<CACHE>/<target_key>/media-<sha>/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe"
export HYPERFRAMES_BROWSER_PATH="<CACHE>/<target_key>/browser-<sha>/chrome-headless-shell-win64/chrome-headless-shell.exe"
export HYPERFRAMES_TELEMETRY_DISABLED=1
node <APP_ROOT>/node_modules/hyperframes/bin/hyperframes.mjs render -o <out.mp4> <PROJECT_DIR>
```
10 秒竖屏约 19 秒出片（300 帧）。三个路径一律从 `<LOCK>` 的 `executable` / `directory` 字段拼，**不要写死版本目录名**。

复用顺序：改文案 → `openmotion_edit_project` 写回 → `lint-project.mjs` → 同步 `render`。不必再走 `export_request`。

---

## 四、成片质检清单（交付前逐项过）

抽帧（首帧 / 钩子屏 / 每一屏中点 / 结尾）：

```sh
ffmpeg -y -loglevel error -ss <t> -i <out.mp4> -frames:v 1 <check_t.png>
```
本次 10 秒片抽 `0.2 / 1.2 / 6.2 / 8.8` 秒。每帧确认：

- [ ] 中文无乱码、无方框、无裁切、无单字孤行；
- [ ] **首帧就饱满**，不要靠长淡入把开头留白（钩子提前到 0.1s 内）；
- [ ] 顶部固定标题、主视觉、主字幕层次清楚，安全区符合 `04-visual-style.md`；
- [ ] 每屏有真实动效（弹入 / 划线 / 数字跳动 / 慢推镜），不是静态晾着；
- [ ] 结尾**利落收尾**：**无底部品牌浮条、无全屏静态尾卡**（v2.3.1 起硬红线）；
- [ ] 画面文字与定稿逐字一致，0 合规红线词；
- [ ] **音频**：默认有声版含音轨、时长对齐画面、旁白不超时不吞字、BGM 音量约 12% 且不盖人声；无声版必须是主动选择（成员要求 / 需挂平台音乐 / 确无真实音源并已说明），**不是默认**；
- [ ] 双封面用**同一套引擎/浏览器**重渲染，保证与成片同风格；检查两行大字与图形不重叠、3:4 版居中在中间 60% 区域。

交付时提醒（v2.3.2 统一口径）：
- 成片含 AI 生成画面 / AI 合成配音，按平台要求勾选「AI 生成」声明。
- **默认交付有声版**（干声旁白 + 真实无版权 BGM 12%，详见 `09-motion-batch-field-notes.md` 第三节）；如另出同配色无声版供平台挂载热门轻音乐（10%–15%），需说明用途。BGM 带署名要求时**必须写明署名信息**。
- 音频自检：`ffprobe` 确认含音轨且时长 10.000s；`ffmpeg -af volumedetect` 确认 mean 约 −18～−20 dB、max 不削波。

---

## 五、降级质量红线（真实用户反馈）

一次降级用 Pillow 画了几何图形版 10 秒 MP4，同事的反馈是 **"效果太差了"**。结论：

- 路径 B 交付的应当是**可粘贴进剪映/即梦的物料清单**（逐屏字幕 / 封面大字 / 配音纯文本 / 实拍镜头关键词 / 6 平台文案），**不要把简陋的本地渲染包装成"成片"交付**——它会被当成正式作品看待，反而拉低观感、还要返工。
- 如果确实需要本地渲染，先问一句是否接受图形动效风，并按 `04-visual-style.md` 做到版式、光影、镜头运动、转场齐备；或者直接说明这是**占位预览片**，不是成品。
- 用户愿意等引擎时，别擅自消耗积分生成 AI 素材；等组件补齐后优先用引擎重做（本次最终交付即 OpenMotion 版，替换掉了本地版）。

---

## 六、速查表

| 现象 | 真因 | 处理 |
|---|---|---|
| "后台还在下载"很久没动 | worker 已退出，status 是死快照 | 查 PID 存活 + `.part` 大小，改离线补齐 |
| `media: failed` 但 exe 已存在 | 宿主 safe-delete 拦截临时目录清理 | 手动重命名归位 + 写 status=ready |
| `EXPORT_WORKER_INTERRUPTED` | 后台 worker 随会话结束被清理 | 前台 `hyperframes render` |
| lint 报中文字体 | 缺 `@font-face` | 补 `src: local(...)` |
| lint 报 root 顶层 clip | 未拆子合成 | 拆到 `compositions/*.html` + `data-composition-src` |
| 渲染日志 GSAP selector 警告 | 选择器/合并 tween 问题 | 抽帧确认动效是否真生效，必要时合并 tween |
| 工具调用拦 `reg.exe` | 宿主安全策略 | 仅警告，忽略，不要重试 |
| 更新 skill 后组件又变未就绪 | 重跑 setup 覆盖了缓存/目录 | 已是最新版就直接跳过升级，先做第一节自检 |
| 子合成覆盖 CSS 部分规则不生效 | `#main .xxx` 后代选择器跨不过子合成边界（`#main` 在 root 的 `index.html`，子合成元素不在其子树内） | 覆盖规则一律用**纯 class 选择器 + `!important`**；颜色尽量走 `:root` 变量 |
| 批量动效片整批同色 / 绿得发闷 | 未按题材轮换配色、深森林绿连出 | 按 `09-motion-batch-field-notes.md` 的 5 套浅色主题轮换，相邻主色相不同 |
| 成片静音被用户打回 | 自写渲染脚本绕开 `batch_runner.py` 的配乐环节 | 复用其 `pick_unique_bgm` + 混音逻辑，默认出有声版；无真实音源才回落无声版并说明 |
