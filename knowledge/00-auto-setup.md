# 自动环境检测与一键依赖安装（Agent 执行手册）

> 核心原则：
> 1. **绝不让非技术同事手动配环境**；
> 2. **绝不让 OpenMotion 安装成为阻塞项**（严禁反复 `git clone` 源码仓库或长时间死等；最多尝试 1 次国内镜像 npm 稳定版安装，失败立刻降级继续交付）。

---

## 一、OpenMotion 极速安装路线（唯一推荐：官方 npm 最新稳定版 + 国内镜像）

> **重要避坑**：国内网络直接 `git clone https://github.com/nexu-io/openmotion.git` + 本地 `npm run build:studio` 极易长时间传输中断。**严禁走源码克隆路线**，统一直接走官方预构建 npm 最新稳定发布包 `@openmotion/app@latest`（内置编译好的 Studio 与 MCP，无需本地构建，只需 `Node.js ≥ 22.18`）。

### 1. 先静默检测（已装则秒过）
先检查当前 Agent 是否已连接 `openmotion` MCP 或本机已有 `@openmotion/app`：
- **已连接 / 已可用**：日常出片直接复用，**不要重复安装**（仅在成员明确说「更新 skill / 升级工具」时执行下方第四节的联动升级）。
- **未安装**：先检查 Node.js 版本：
  ```sh
  node -v
  ```
  - 需 `Node.js ≥ 22.18`（如 `22.22.x` 即满足）。
  - 若未安装或低于 `22.18`，按系统自动安装 LTS 版（macOS：`brew install node`；Windows：`winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements`）；若权限受限无法自动装，**不要卡死**，直接跳到下方「五、非阻塞降级原则」。

### 2. 一键安装 `@openmotion/app@latest`（直走国内镜像，防官方源重置）

先用一句大白话告知同事：
> “首次出片正在用国内镜像为你安装最新版 OpenMotion（约 30–60 秒），装完之后每次都能直接出片。”

通过环境变量锁定 `npm_config_registry=https://registry.npmmirror.com`（确保 `npx` 及其内部子进程全程走国内镜像，不被重置回 npm 官方源），并按当前实际宿主替换 `<HOST>`（`WorkBuddy` → `workbuddy`；`Claude Code` → `claude`；`Codex` → `codex`；`Cursor` → `cursor`；其他桌面 Agent 可省略 `--host` 直接安装核心运行库）：

- **macOS / Linux**：
  ```sh
  npm_config_registry=https://registry.npmmirror.com npm_config_fetch_retries=0 npx --yes @openmotion/app@latest setup --host <HOST>
  ```
- **Windows (PowerShell)**：
  ```powershell
  $env:npm_config_registry="https://registry.npmmirror.com"
  $env:npm_config_fetch_retries="0"
  npx --yes @openmotion/app@latest setup --host <HOST>
  ```

安装完成后：
- **必做：导出能力自检（安装成功 ≠ 能导出）**：按 `knowledge/06-rendering-playbook.md` 第一节确认 `browser` / `media` 都是 `ready` 且 `capabilities.export === true`。未就绪时走该手册第二节离线补齐（国内镜像 + sha256 缓存注入，Agent 可跑 `scripts/fetch_om_components.py`）；**状态文件只是快照，先查下载进程是否还活着，别把"进程已死"当成"网速慢"而空等**。
- 按输出完成本地 Studio 启动与 MCP 连接，后续会话直接复用，无需重装。
- 若本机已装浏览器（如 `ego-lite` / Chrome / Edge），优先复用已有浏览器，不强求额外下载 Chrome。

---

## 二、HeyGen HyperFrames 自动安装（`实拍混剪` / `即梦片` / `Flow片` 高画质渲染引擎）

官方仓库：`https://github.com/heygen-com/hyperframes`（需要 `Node.js ≥ 22` 与 `FFmpeg`）。
当同事首次使用 **`实拍混剪`**、**`即梦片`** 或 **`Flow片`** 时，自动检测并安装：

1. **先静默检测**：
   ```sh
   hyperframes --version
   ```
   若已安装且 `npx hyperframes doctor --json` 中 `ok === true`，直接复用。
2. **未安装时走国内镜像一键全局安装 + 补齐浏览器内核**：
   - **macOS / Linux**：
     ```sh
     npm_config_registry=https://registry.npmmirror.com npm install -g hyperframes
     npx hyperframes browser ensure
     npx hyperframes doctor --json
     ```
   - **Windows (PowerShell)**：
     ```powershell
     $env:npm_config_registry="https://registry.npmmirror.com"
     npm install -g hyperframes
     npx hyperframes browser ensure
     npx hyperframes doctor --json
     ```
   - 若同事需要让当前 AI 工具也获得官方 HyperFrames 技能支持，可顺手执行：`npx skills add heygen-com/hyperframes`。

---

## 三、`ego-lite`（`ego-browser`）自动检测与安装（`Flow片` 全自动前置必需）

使用 **`Flow片`**（Google Flow 全自动生视频）时，**必须依赖 `ego-lite`（`ego-browser`）**复用已登录的 Google AI Pro 会话：

1. **先检测是否就绪**：
   - macOS / Linux：`command -v ego-browser && ego-browser nodejs -e "console.log('ego-browser ready')"`
   - Windows (PowerShell)：`Get-Command ego-browser; ego-browser nodejs -e "console.log('ego-browser ready')"`
2. **未安装时的自动处理**：
   - **macOS**：直接引导/运行 `ego-browser` 官方 macOS 安装流程（下载对应 arm64/x64 DMG 安装 `ego lite.app` 到 `/Applications` 并拉起），提示同事在弹出的 `ego lite` 窗口里点完首次引导（自动把 `ego-browser` 注册到 `~/.local/bin`），再验证 `ego-browser ready`。
   - **Windows**：目前官方无静默脚本，直接为同事打开下载页 `https://lite.ego.app/` 并给出 3 步极简指引：① 核对官方发布方后运行安装包；② 打开 `ego lite` 完成首次引导并登录 Google Flow；③ 新开终端验证 `ego-browser ready`。
3. 就绪后立刻切入 `knowledge/08-ai-video-engines.md` 第四节执行全自动生成。

---

## 四、即梦 CLI（`dreamina`）与可选免费配音依赖

1. **即梦 CLI（`dreamina`，仅在使用 `即梦片` 时检测）**：
   - 检测：`dreamina --version && dreamina user_credit`。
   - 未登录时执行 `dreamina login`（OAuth Device Flow），把终端输出的授权链接与 `user_code` 发给同事扫码完成，**保持命令运行直至打印登录成功后再明确回复同事**。
   - 若未安装 `dreamina`，告知同事按即梦官方 CLI 指引安装后再试（绝不自行编造假命令）。
2. **免费中文配音（`edge-tts`，用于 `实拍混剪`、`省点混剪` 与 `动效片` 默认有声版旁白）**：
   - 走国内清华镜像秒装（已装则跳过）：
     ```sh
     python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -U edge-tts
     ```
   - 默认音色：`zh-CN-XiaoxiaoNeural` 或 `zh-CN-YunxiNeural`（输出纯人声干声，BGM 由后期混音叠加，见 `09-motion-batch-field-notes.md` 第三节）。
   - `动效片` 默认有声版也用此引擎：40–55 字、rate +10%、合成后 `atempo` 压进 9.4 秒。
3. **音视频合成（`ffmpeg`）**：
   - 若缺失则自动装（macOS：`brew install ffmpeg`；Windows：`winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements`）。

---

## 五、非阻塞降级原则（红线：绝不卡死同事）

1. **最多尝试 1 次**：上述 `@openmotion/app@latest` 或 `hyperframes` 安装命令只尝试 1 次（禁止反复重试、禁止切回 `git clone` 源码仓库拉取 10+ 分钟）。
2. **失败立刻降级继续干活**：若因网络/权限/Node 版本安装失败，**不要临场手写粗糙 HTML 拼低质视频**，而是：
   - 用 1 句大白话说明原因（例如“当前网络/Node 环境暂未装上渲染引擎，先不耽误你出片”）；
   - 立刻交付可直接复制进剪映/即梦的「逐屏大字/字幕清单 + 封面双行大字 + 纯净配音文本 + 6 平台发布文案」，确保同事当场就能完成任务。
3. **质量红线（来自真实反馈）**：曾有降级版用简单几何图形渲染出 MP4，同事评价「效果太差」。**不要把简陋本地渲染包装成「成片」交付**；若确需本地渲染，先确认对方接受图形动效风，或明确标注为占位预览片并说明后续用引擎重做。详见 `knowledge/06-rendering-playbook.md` 第五节。

---

## 六、Skill 更新时自动联动升级依赖（版本同步机制）

当成员说 **「更新一下 `yidehai-video-skill`」** / **「同步最新视频助手」** 时，按以下 4 步一站式升级（同样遵循非阻塞原则，单步失败不阻断整体）：

1. **拉取最新版 Skill 与知识库**：
   - 从 `https://github.com/yidehai-tech/yidehai-video-skill` 更新本 Skill 到最新版本（覆盖更新 `SKILL.md`、`knowledge/` 及 `scripts/`）。
2. **联动升级 OpenMotion（已装时检查）**：
   - 若本机已是最新版，**直接跳过，不要为「升级」重跑 setup**——重装可能覆盖已手动补齐的 native 组件；仅在需要升级时走国内镜像执行 `@openmotion/app@latest setup --host <HOST>` 并做导出自检。
3. **联动升级 HeyGen HyperFrames 与已装可选插件**：
   - 若本机已安装 `hyperframes`，顺手走国内镜像升级：`npm_config_registry=https://registry.npmmirror.com npm install -g hyperframes`；
   - 若本机已安装 `edge-tts`，顺手走清华镜像升级：`python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -U edge-tts`（未装过则跳过）。
4. **简明汇报结果**：用 2–3 行告诉同事：① Skill 已更新到的版本号；② 依赖工具是否已是最新（若有失败项一句带过，不影响继续出片）。
