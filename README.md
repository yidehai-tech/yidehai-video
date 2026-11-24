# 亿德海团队短视频创作 Skill（`yidehai-video-skill`）

面向项目组非技术成员的一站式短视频创作与批量出片 Skill：内置亿德海合规红线、真实业务规则、爆款写稿方法论、首次本地素材路径记忆与全局防重账本。**全面兼容市面上所有主流 AI Agent 工具**——无论你用的是桌面执行型工具（**WorkBuddy、Claude Code、Codex、Cursor、Antigravity、OpenClaw** 等），还是对话/知识库型工具（**豆包、通义千问、Kimi、扣子** 等），均可无缝接入。

---

## 一、支持 7 大中文视频形态（直接说中文，不用记英文工具名）

| 形态 | 费用 | 适用场景 |
| :--- | :--- | :--- |
| **`大字报`** | 免费 0 点 | 8.8 秒风景空镜 + 满屏大字，9 秒直出，高频日更主力 |
| **`动效片`** | 免费 0 点 | 10 秒多屏动态卡片 + 图形动效 + AI 旁白（OpenMotion） |
| **`实拍混剪`** | 免费 0 点 | 本地实拍视频/图片（全局防重）+ 免费干声旁白 → HeyGen HyperFrames 渲染 |
| **`图文故事片`** | 按所选图源定（可 0 点） | 4–6 张分镜图平滑推镜短视频 + **小红书 3:4 轮播套图（一鱼两吃）**，图源由你 4 选 1（宿主内置生图 / 即梦 / 免费 API / 本地图片） |
| **`即梦片`** | 扣即梦积分（显式点名才用） | `dreamina` CLI 全自动，支持「纯即梦」和「省积分混剪（即梦 5s 开场 + 本地实拍）」 |
| **`Flow片`** | 扣 Google 点数（显式点名才用） | `ego-lite` 全自动 Google Flow，支持 `Omni 1.2 Flash` 口播与 `Veo 3.1 Lite` 10 点省点混剪 |
| **`口播包装`** | 免费 0 点 | 真人实拍口播视频 + MotionGit 官方免费模板包装 |

---

## 二、给同事的 3 步使用说明（全平台 Agent 通用）

1. **导入这 1 个 Skill（按你使用的工具选一种）**：
   - **WorkBuddy / Claude Code / Codex / Cursor / Antigravity / OpenClaw（桌面执行型 · 全自动出片）**：
     - 对话框直接发：`请从 https://github.com/yidehai-tech/yidehai-video-skill 安装 yidehai-video-skill`
     - 或命令行一键安装：`npx skills add yidehai-tech/yidehai-video-skill`
   - **豆包 / 通义千问 / Kimi / 扣子（纯对话/知识库型 · 满血脚本与 Prompt 工厂）**：
     - 将仓库内的 `SKILL.md` 与 `knowledge/01–08` 上传到智能体/项目知识库，即可直接对话产出 0 违规脚本、双封面大字、6 平台文案与可直接粘贴进即梦/Flow/剪映的防穿帮 Prompt。
2. **首次开工配一次本地素材路径**（桌面型工具首次问 1 次，以后永久记住）：
   - 第一次对话时，助手会一次性问你的**本地实拍素材文件夹路径**（视频/图片，用于实拍混剪和省点混剪）、风景空镜目录（可选）和 MotionGit 免费模板目录（可选）；直接贴路径或回复「跳过」即可。
3. **直接说需求出片**：
   - 例：“帮我做一条**大字报**” / “批量出 **20 条大字报**”
   - 例：“用本地素材帮我做一条 **0 点实拍混剪**”
   - 例：“用**即梦**做一条省积分混剪视频”
   - 例：“用 **Flow** 省点轮换出一条旧羽绒服回收视频”

---

## 三、目录结构

```text
yidehai-video-skill/
├── SKILL.md                               # 核心 6 形态工作流、首次初始化引导与自检规则
├── README.md                              # 本使用与更新说明
├── knowledge/
│   ├── 00-auto-setup.md                   # OpenMotion / HeyGen HyperFrames / ego-lite / dreamina 自动检测与安装
│   ├── 01-brand-rules.md                  # 合规硬红线与无浮条利落收尾规范（最高优先级）
│   ├── 02-business-faq.md                 # 真实业务规则（起收标准/品类/流程，对外脱敏版）
│   ├── 03-copy-formula.md                 # 写稿方法论与四维选题防枯竭矩阵
│   ├── 04-visual-style.md                 # 竖屏安全区、双封面与大字报专项模板
│   ├── 05-good-examples.md                # 已验证的过审脚本样本
│   ├── 06-rendering-playbook.md           # OpenMotion 组件补齐、lint、同步渲染与抽帧质检
│   ├── 07-poster-batch-field-notes.md     # 大字报批量出片实战避坑指南
│   ├── 08-ai-video-engines.md             # 即梦 CLI / Google Flow(ego-lite) / 实拍混剪 / MotionGit 实操手册
│   ├── 09-motion-batch-field-notes.md     # 动效片批量实战手册（5 套浅色配色轮换 / 旁白+12% BGM 混音 / 子合成 CSS 避坑）
│   ├── 10-storybook-workflow.md           # 图文故事片一鱼两吃手册（图源 4 选 1 护栏 + 推镜视频 + 小红书 3:4 轮播）
│   └── media-catalog.json                 # 在线免版权 BGM 备用清单（GitHub Releases 托管，需实测可用性）
└── scripts/
    ├── media_manager.py                   # 本地目录记忆、实拍素材防重抽取与在线空镜/图片/BGM 拉取
    ├── render_poster.py                   # 离线极速大字报渲染器（成片 + 双封面）
    ├── package_ai_video.py                # 通用 AI/实拍视频包装器（HeyGen HyperFrames · 无品牌浮条）
    ├── storybook_builder.py               # 图文故事片一鱼两吃构建器（推镜成片 + 小红书 3:4 轮播套图）
    ├── dreamina_runner.py                 # 即梦官方 CLI 防呆调度器（防重复扣分 + 断点续查）
    ├── batch_runner.py                    # 批量出片调度器与可视化审片台
    ├── motion_templates.py                # 动效片备选母版
    └── fetch_om_components.py             # OpenMotion 组件镜像补齐脚本
```

---

## 四、一键更新

群里通知更新后，直接对你使用的桌面 Agent（WorkBuddy / Claude Code / Codex / Cursor 等）说：**`帮我更新一下 yidehai-video-skill`** —— 会自动同步最新知识库与脚本，并按需升级本机已装的 `hyperframes` / `OpenMotion` / `edge-tts`。
