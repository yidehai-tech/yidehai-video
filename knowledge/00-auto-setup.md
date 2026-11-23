# 自动环境检测与一键依赖安装（Agent 执行手册）

> 核心原则：
> 1. **绝不让非技术同事手动配环境**；
> 2. **绝不让 OpenMotion 安装成为阻塞项**（严禁反复 `git clone` 源码仓库或长时间死等；最多尝试 1 次国内镜像 npm 稳定版安装，失败立刻降级继续交付）。

---

## 一、OpenMotion 极速安装路线（唯一推荐：官方 npm 稳定版 + 国内镜像）

> **重要避坑**：国内网络直接 `git clone https://github.com/nexu-io/openmotion.git` + 本地 `npm run build:studio` 极易长时间传输中断。**严禁走源码克隆路线**，统一直接走官方预构建 npm 发布包 `@openmotion/app@0.2.1`（内置编译好的 Studio 与 MCP，无需本地构建，只需 `Node.js ≥ 22.18`）。

### 1. 先静默检测（已装则秒过）
先检查当前 Agent 是否已连接 `openmotion` MCP 或本机已有 `@openmotion/app`：
- **已连接 / 已可用**：直接复用，**不要重装**。
- **未安装**：先检查 Node.js 版本：
  ```sh
  node -v
  ```
  - 需 `Node.js ≥ 22.18`（如 `22.22.x` 即满足）。
  - 若未安装或低于 `22.18`，按系统自动安装 LTS 版（macOS：`brew install node`；Windows：`winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements`）；若权限受限无法自动装，**不要卡死**，直接跳到下方「三、非阻塞降级」。

### 2. 一键安装 `@openmotion/app@0.2.1`（直走国内镜像，防官方源重置）

先用一句大白话告知同事：
> “首次出片正在用国内镜像为你安装 OpenMotion 稳定版（约 30–60 秒），装完之后每次都能直接出片。”

通过环境变量锁定 `npm_config_registry=https://registry.npmmirror.com`（确保 `npx` 及其内部子进程全程走国内镜像，不被重置回 npm 官方源），并根据当前宿主传入 `--host`（WorkBuddy 传 `--host workbuddy`；Codex 传 `--host codex`；Claude Code 传 `--host claude`）：

- **macOS / Linux**：
  ```sh
  npm_config_registry=https://registry.npmmirror.com npm_config_fetch_retries=0 npx --yes @openmotion/app@0.2.1 setup --host workbuddy
  ```
- **Windows (PowerShell)**：
  ```powershell
  $env:npm_config_registry="https://registry.npmmirror.com"
  $env:npm_config_fetch_retries="0"
  npx --yes @openmotion/app@0.2.1 setup --host workbuddy
  ```

安装完成后：
- 按输出完成本地 Studio 启动与 MCP 连接，后续会话直接复用，无需重装。
- 若本机已装浏览器（如 `ego-lite` / Chrome / Edge），优先复用已有浏览器，不强求额外下载 Chrome。

---

## 二、可选免费中文配音依赖（按需安装，同样不阻塞）

仅当同事明确要求加**免费纯人声干声旁白**时才检查（无声大字报/动效片不需要此步）：
- **配音（`edge-tts`）**：走国内清华镜像秒装（已装则跳过）：
  ```sh
  python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -U edge-tts
  ```
  默认音色：`zh-CN-XiaoxiaoNeural`（纯人声无 BGM）。
- **音视频合成（`ffmpeg`）**：若缺失则自动装（macOS：`brew install ffmpeg`；Windows：`winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements`）。

---

## 三、非阻塞降级原则（红线：绝不卡死同事）

1. **最多尝试 1 次**：上述 `@openmotion/app@0.2.1` 命令只尝试 1 次（禁止反复重试、禁止切回 `git clone` 源码仓库拉取 10+ 分钟）。
2. **失败立刻降级继续干活**：若因网络/权限/Node 版本安装失败，**不要临场手写粗糙 HTML 拼低质视频**，而是：
   - 用 1 句大白话说明原因（例如“当前网络/Node 环境暂未装上 OpenMotion，先不耽误你出片”）；
   - 立刻交付可直接复制进剪映/即梦的「逐屏大字/字幕清单 + 封面双行大字 + 纯净配音文本 + 6 平台发布文案」，确保同事当场就能完成任务。
