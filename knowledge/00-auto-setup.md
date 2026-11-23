# 自动环境检测与一键依赖安装（Agent 执行手册）

> 目标：**绝不让非技术同事手动去 GitHub 下载、配环境或装插件。**
> 当同事首次使用本 Skill 要求“出片”或“安装环境”时，由 AI Agent 自动按以下步骤检测、拉取并配置依赖；已安装的环境直接复用，不重复下载。

---

## 一、检测与安装顺序（幂等执行）

首次安装前，先用一句大白话告知同事：
> “首次出片需要自动帮你安装一下 OpenMotion 视频引擎（大约 2–3 分钟），装完以后每次都能直接出片，你先稍等一下。”

### 1. 基础运行环境检查（Node.js ≥ 22.18 & Git）

先静默检查：
```sh
node -v && git --version
```
- 如果均已存在且 Node.js 版本 `>= 22.18`：跳过此步。
- 如果缺失或版本过低，按操作系统自动安装（如遇权限弹窗，用大白话提示同事点“允许”）：
  - **macOS**：`brew install node git`
  - **Windows (PowerShell)**：`winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements` 与 `winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements`

### 2. 自动安装 OpenMotion（视频引擎 + MCP）

先检查当前 Agent 是否已连接 `openmotion` MCP，或本地是否已有 `~/yidehai-tools/openmotion`（Windows 为 `%USERPROFILE%\yidehai-tools\openmotion`）：
- **已连接 / 已存在**：直接复用，无需重装；若未启动则直接在该目录运行 `npm start` 启动本地 Studio。
- **未安装**：依次自动执行以下官方命令（不下载大体积 LFS 示例视频，节省磁盘与时间）：

1. 安装官方 `openmotion` Skill（让 Agent 获得完整的 OpenMotion Studio & MCP 操控能力）：
   ```sh
   npx --yes skills add nexu-io/openmotion --skill openmotion --yes
   ```
2. 浅克隆并构建本地 OpenMotion Studio：
   - **macOS / Linux**：
     ```sh
     mkdir -p ~/yidehai-tools
     git -c filter.lfs.process= -c filter.lfs.smudge= -c filter.lfs.required=false clone --depth 1 --single-branch --branch main https://github.com/nexu-io/openmotion.git ~/yidehai-tools/openmotion
     cd ~/yidehai-tools/openmotion && npm ci && npm run build:studio
     ```
   - **Windows (PowerShell)**：
     ```powershell
     New-Item -ItemType Directory -Force -Path "$HOME\yidehai-tools" | Out-Null
     git -c filter.lfs.process= -c filter.lfs.smudge= -c filter.lfs.required=false clone --depth 1 --single-branch --branch main https://github.com/nexu-io/openmotion.git "$HOME\yidehai-tools\openmotion"
     Set-Location "$HOME\yidehai-tools\openmotion"
     npm ci
     npm run build:studio
     ```
3. 参照克隆目录内的 `docs/install.md` 完成本地 Studio 启动与 MCP 连接，并复用该工作区。

### 3. 可选免费中文配音依赖（`edge-tts` + `ffmpeg`，按需自动装）

仅当同事要求给视频加**免费纯人声干声旁白**时才检查安装（无声动效片不需要此步）：
- 检查 `edge-tts --version`：若未安装且本机有 Python，自动执行：
  ```sh
  python3 -m pip install -U edge-tts
  ```
  （Windows 用 `py -m pip install -U edge-tts` 或 `python -m pip install -U edge-tts`）。
  默认使用自然中文女声：`zh-CN-XiaoxiaoNeural`，生成纯人声干声 MP3（不加 BGM）。
- 检查 `ffmpeg -version`：若缺失则自动安装：
  - **macOS**：`brew install ffmpeg`
  - **Windows**：`winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements`

---

## 二、降级兜底规则（绝不卡死同事）

如果因公司网络限制、系统权限拦截或本机性能不足导致 OpenMotion 安装/构建失败：
1. 用一句简单的话告诉同事具体卡在哪一步（不丢大段技术报错日志）；
2. **立刻自动切换为路径 B（免安装兜底模式）**：直接交付「可直接复制进剪映/即梦的逐屏字幕清单 + 封面大字 + 配音纯文本 + 6 平台发布文案」，保证同事当场依然能完成出片。
