# yidehai-video-skill

![Version](https://img.shields.io/badge/version-2.6.6-2B8A3E)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-blue)
![Standard](https://img.shields.io/badge/Agent%20Skills-SKILL.md-orange)

面向 **亿德海（yidehai）旧衣回收** 垂直场景的开源 AI Agent 短视频创作与批量生产 Skill。  
内置业务事实库、多平台合规硬拦截、四维选题防枯竭矩阵、全局素材防重账本与跨平台渲染管线，兼容市面上所有主流桌面执行型与对话/知识库型 AI Agent 工具。

---

## 核心特性

- **7 大生产轨道统一调度**：覆盖 0 成本高频日更（`大字报` / `动效片` / `实拍混剪` / `口播包装`）、一鱼两吃（`图文故事片`）与付费高拟真 AI 视频（`即梦片` / `Flow片`）。
- **全平台 Agent 自动分级适配**：自动识别运行环境（L1 桌面执行型 / L2 轻沙箱型 / L3 纯对话知识库型），在任意工具中开箱即用。
- **积分与费用自主选择护栏**：默认仅使用 0 积分免费轨道；调用宿主内置生图、即梦 CLI 或 Google Flow 前均要求显式选择与确认，并具备提交前原子落盘防重复扣分机制。
- **统一成片质量标准**：默认「旁白 + 12% 真实无版权 BGM」、无底部品牌浮条与全屏静态尾卡、自动产出 `9:16` + `3:4` 双封面与 8 帧质检联系图。
- **本机配置与防重隔离**：素材目录、API Key 与防重账本全部持久化在 `~/.yidehai-video/`，与 Skill 仓库彻底解耦。

---

## 支持的视频形态

| 形态 | 标识 | 费用口径 | 旁白 | 底层管线 | 适用场景 |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **`大字报`** | `poster` | 免费（0 点） | ✕ | `render_poster.py`（离线直出） | 8.8s 风景空镜 + 满屏大字，高频日更主力 |
| **`动效片`** | `motion` | 免费（0 点） | ✓（AI） | OpenMotion / HyperFrames | 10s 多屏卡片动效 + 5 套浅色主题轮换 |
| **`实拍混剪`** | `montage` | 免费（0 点） | ✓（AI） | `package_ai_video.py` + HeyGen HyperFrames | 本地实拍视频/图片防重拼接 + 干声旁白 |
| **`图文故事片`** | `storybook` | 按图源定（可 0 点） | ✓（AI） | `storybook_builder.py` + HeyGen HyperFrames | 4–6 张分镜图平滑推镜成片 + **小红书 3:4 轮播套图** |
| **`即梦片`** | `dreamina` | 扣即梦积分（Opt-in） | ✓ | `dreamina_runner.py` + HeyGen HyperFrames | 纯即梦口播或「即梦 5s 开场 + 本地实拍」省积分混剪 |
| **`Flow片`** | `flow` | 扣 Google 点数（Opt-in） | ✓ | `ego-lite` + Google Flow + HeyGen HyperFrames | `Omni 1.2 Flash` 口播或 `Veo 3.1 Lite` 10 点省点混剪 |
| **`口播包装`** | `motiongit` | 免费（0 点） | ✓（原声） | MotionGit 官方免费模板 | 真人实拍口播视频的高质感动态风格化包装 |

---

## 快速安装

### 方式一：通过 `skills` CLI 安装（推荐）

适用于 **Claude Code、Codex、Cursor、Antigravity、OpenClaw** 等支持标准 Skill CLI 的工具：

```bash
npx skills add yidehai-tech/yidehai-video-skill
```

### 方式二：在桌面 Agent 对话框中直接导入

适用于 **WorkBuddy、豆包桌面版** 等支持通过仓库链接安装 Skill 的桌面客户端，直接发送：

```text
请从 https://github.com/yidehai-tech/yidehai-video-skill 安装 yidehai-video-skill
```

> **一步到位无二次确认**：Agent 克隆/下载到独立目录（推荐 `~/.yidehai-video/skill-repo`）后运行一次 `python3 scripts/link_skill.py`（可附带 `--extra-skills-dir`），会自动同时完成跨宿主安全挂载以及必备免费基础依赖（`FFmpeg`/`FFprobe`、`edge-tts`、`Pillow`）的安装与校验，无需二次询问用户。

### 方式三：纯对话 / 知识库型 Agent 接入

适用于 **豆包、通义千问、Kimi、扣子、ChatGPT Projects** 等无本地终端环境的工具：  
将本仓库的 `SKILL.md` 与 `knowledge/01–10` 导入对应智能体或项目知识库，即可自动切换为 **编导 + 合规自检 + Prompt 工厂模式**，直接产出合规脚本、双封面文案及可直接粘贴进即梦/Flow/剪映的防穿帮提示词。

### 多 Agent 工具共用同一项目（自动自愈挂载，无需手动折腾）

不同桌面 Agent 默认扫描各自的私有目录。`scripts/link_skill.py` 内置覆盖国内外主流宿主（`WorkBuddy`、`豆包`、`通义千问`、`OpenClaw`、`Claude Code`、`Codex`、`Gemini/Antigravity`、`Cursor`、`Trae`、`Windsurf`、`Qoder`、`Kiro`、`Cline`、`Roo`、`Copilot`、`OpenCode` 以及开放标准 `.agents/skills` / `.skills`），**仅对本机已安装的宿主自动挂载**（macOS/Linux 使用软链；**Windows 默认使用安全镜像副本**，避免部分宿主清理 `.skills` 目录时穿透 Junction 误删真源），并在项目根目录自动写入跨工具通用的 `AGENTS.md` 兜底入口。

- **非技术用户直接用自然语言**：在任意新换的桌面 Agent 对话框里说一句：
  ```text
  请帮我把 yidehai-video-skill 自动挂载到当前项目和你自己的技能目录里
  ```
  Agent 会自动识别自身目录并静默完成挂载（若未在默认列表里，也会由 Agent 主动调用 `--extra-skills-dir` 自愈解决，无需用户手敲命令）。
- **开发者手动执行（可选）**：
  ```bash
  # 推荐将仓库克隆到独立持久化目录（如 ~/.yidehai-video/skill-repo），勿放在某个单一 Agent 私有目录内以免被宿主清理
  python3 scripts/link_skill.py --project-dir "/path/to/your-video-project"
  ```

---

## 快速上手

### 1. 配置必需素材源与免费 API Key（严禁缺配出残缺作品）

为避免全员撞画面且确保每条成片都具备完整画质与音轨，本 Skill **不预置公用风景空镜**，并在生成前执行 `preflight` 硬校验（缺背景视频或音乐源时直接拦截，绝不回落纯色底或无声半成品）。所有配置一次写入 `~/.yidehai-video/config.json` 永久记住：

```bash
# 校验目标轨道所需配置是否齐备（poster / motion / montage / storybook / motiongit）
python3 scripts/media_manager.py preflight --track poster

# 查看当前本机配置（自动脱敏，不回显密钥）
python3 scripts/media_manager.py config --show

# 配置大字报风景空镜（Pexels / Pixabay 免费 API Key 或本地空镜目录二选一，必配）
python3 scripts/media_manager.py config --set-pexels-key "<YOUR_PEXELS_KEY>"
python3 scripts/media_manager.py config --set-pixabay-key "<YOUR_PIXABAY_KEY>"
python3 scripts/media_manager.py config --add-bg-dir "/path/to/scenic"

# 配置背景音乐源（Jamendo 免费音乐 Client ID 或本地免版权音乐目录）
python3 scripts/media_manager.py config --set-jamendo-id "<YOUR_JAMENDO_CLIENT_ID>"
python3 scripts/media_manager.py config --add-bgm-dir "/path/to/bgm"

# 配置本地业务实拍目录（供实拍混剪与省点混剪防重抽取）
python3 scripts/media_manager.py config --add-footage-dir "/path/to/footage"

# 设置图文故事片默认生图来源（ask / host_tool / dreamina / free_api / local）
python3 scripts/media_manager.py config --set-image-source ask
```

### 2. 对话式调用示例

```text
帮我做一条换季清衣柜的大字报视频
帮我批量生成 20 条旧衣回收视频（默认 50% 大字报 + 50% 动效片）
用本地实拍素材做一条 0 点实拍混剪
帮我做一条旧羽绒服回收的图文故事片（同步出小红书轮播图）
用即梦 CLI 做一条省积分混剪视频
用 Google Flow 省点轮换出一条旧鞋旧包回收视频
```

---

## 多宿主分级适配

| 等级 | 宿主类型 | 代表工具 | 运行模式 |
| :--- | :--- | :--- | :--- |
| **L1** | 完整桌面执行型 | WorkBuddy、Claude Code、Codex、Cursor、Antigravity、Windsurf、OpenClaw | 全 7 轨道自动检测依赖、渲染成片、抽帧质检并按日期归档 |
| **L2** | 轻终端 / 受限沙箱型 | 云端容器、受限终端 Agent | 优先运行纯本地离线脚本，缺少渲染引擎时平滑降级 |
| **L3** | 纯对话 / 知识库型 | 豆包、通义千问、Kimi、扣子、ChatGPT Projects | 自动跳过本地脚本检测，输出合规脚本 + 双封面字 + 防穿帮 Prompt |

---

## 目录结构

```text
yidehai-video-skill/
├── SKILL.md                               # Skill 入口：L1/L2/L3 适配、7 形态工作流与合规自检
├── README.md                              # 项目说明文档
├── knowledge/
│   ├── 00-auto-setup.md                   # OpenMotion / HeyGen HyperFrames / ego-lite / dreamina 自动检测与安装
│   ├── 01-brand-rules.md                  # 最高优先级：合规禁用词、无浮条利落收尾与统一 12% BGM 音频口径
│   ├── 02-business-faq.md                 # 脱敏版公开业务规则（起收门槛、可收品类、流程口径）
│   ├── 03-copy-formula.md                 # 写稿方法论与四维选题防枯竭矩阵
│   ├── 04-visual-style.md                 # 竖屏安全区、5 套浅色主题轮换、双封面与大字报版式规范
│   ├── 05-good-examples.md                # 已验证过审脚本与大字报样本
│   ├── 06-rendering-playbook.md           # OpenMotion 组件补齐、lint、同步渲染与抽帧质检
│   ├── 07-poster-batch-field-notes.md     # 大字报批量出片实战避坑指南
│   ├── 08-ai-video-engines.md             # 即梦 CLI / Google Flow(ego-lite) / 实拍混剪 / MotionGit 实操手册
│   ├── 09-motion-batch-field-notes.md     # 动效片批量实战手册（配色轮换 / 旁白+12% BGM 混音 / 子合成避坑）
│   ├── 10-storybook-workflow.md           # 图文故事片一鱼两吃手册（图源 4 选 1 护栏 + 推镜视频 + 3:4 轮播）
│   └── media-catalog.json                 # 在线免版权 BGM 备用清单（GitHub Releases 托管）
└── scripts/
    ├── media_manager.py                   # 本机配置、共享合规校验、跨进程文件锁、素材防重与在线拉取
    ├── render_poster.py                   # 大字报离线渲染器（1080x1920 成片 + 9:16 & 3:4 双封面）
    ├── package_ai_video.py                # 通用 AI/实拍视频包装器（HeyGen HyperFrames · 12% BGM · 8 帧质检）
    ├── storybook_builder.py               # 图文故事片构建器（推镜短视频 + 小红书 3:4 轮播套图）
    ├── dreamina_runner.py                 # 即梦 CLI 防呆调度器（提交前原子落盘、防重复扣分、断点续查）
    ├── batch_runner.py                    # 批量出片调度器（断点续跑 + 可视化审片台 review.html）
    ├── motion_templates.py                # 动效片三套母版（5 套浅色主题轮换，无品牌浮条）
    ├── fetch_om_components.py             # OpenMotion native 组件镜像补齐与 sha256 校验脚本
    └── link_skill.py                      # 跨宿主一键软链/联接挂载工具（解决多 Agent 目录孤岛）
```

---

## 环境要求与版本更新

- **基础运行环境（L1 桌面执行型）**：`Python 3.10+`、`FFmpeg / FFprobe`、`Pillow`；使用 `动效片` / `实拍混剪` / `AI 包装` 时需 `Node.js ≥ 22`（国内镜像自动安装 `OpenMotion` 与 `HeyGen HyperFrames`）。
- **同步最新版本**：在桌面 Agent 中直接执行：
  ```text
  更新一下 yidehai-video-skill
  ```
  或通过 `npx skills add yidehai-tech/yidehai-video-skill` 重新拉取。
