# 亿德海团队短视频创作 Skill（`yidehai-video-skill`）

面向项目组非技术成员的极简短视频创作 Skill：内置亿德海合规红线、真实业务规则、爆款写稿方法论与视觉规范，装进 **WorkBuddy**（或兼容 `SKILL.md` 的 AI 工具）即可直接对话出稿、联动 **OpenMotion** 等工具快速出片，无需每次反复交代项目背景。

---

## 一、给同事的 3 步使用说明

1. **安装/导入这 1 个 Skill 即可**（不需要单独去装 OpenMotion、剪辑插件或配音工具，首次出片时 AI 会自动帮你检测并拉取安装所需依赖）。
2. **直接说需求**（不用交代公司背景）：
   - 例：“帮我做一条**换季清衣柜**的 10 秒短视频”
   - 例：“帮我做一条**旧鞋旧包回收**的**大字报视频**（深绿/米白风）”
   - 例：“写一条**旧羽绒服回收**的视频脚本并给 6 平台文案”
3. **选切角 → 定稿 → 自动出片**：
   - AI 会先给 3 个切角，回复“选第 X 个”拿到合规脚本、分屏建议、双封面字和 6 平台文案；
   - 回复“定稿，出片”，AI 会自动检查/安装 OpenMotion 并生成可预览的竖屏视频，看一眼没问题直接导出 MP4。

---

## 二、目录结构

```text
yidehai-video-skill/
├── SKILL.md                     # 核心工作流与自检规则
├── README.md                    # 本使用与更新说明
├── knowledge/
│   ├── 00-auto-setup.md         # 自动环境检测与 OpenMotion / 配音依赖一键安装手册
│   ├── 01-brand-rules.md        # 短视频合规硬红线 + 方案A收尾规范（最高优先级）
│   ├── 02-business-faq.md       # 真实业务规则（起收标准/品类/流程，对外脱敏版）
│   ├── 03-copy-formula.md       # 写稿方法论（第零步切角/获客4.0/感觉词/字数）
│   ├── 04-visual-style.md       # 竖屏视觉规范 + OpenMotion 动效、大字报模板与双封面约束
│   ├── 05-good-examples.md      # 已验证的过审样本
│   └── 06-rendering-playbook.md # 「装好了却导不出 MP4」：组件离线补齐 / lint / 同步渲染 / 抽帧质检
└── scripts/
    └── fetch_om_components.py   # Agent 专用：按 runtime-lock 走镜像+分段下载并 sha256 校验组件
```

---

## 三、线上安装与团队一键更新

线上公开仓库：`https://github.com/yidehai-tech/yidehai-video-skill`

- **同事首次安装**：
  - 在 WorkBuddy 中直接发一句：`请从 https://github.com/yidehai-tech/yidehai-video-skill 安装 yidehai-video-skill`
  - 或在支持 `skills` CLI 的环境中执行：`npx skills add yidehai-tech/yidehai-video-skill`
- **同事一键更新**：
  - 群里通知更新后，在 WorkBuddy 中直接说：`帮我更新一下 yidehai-video-skill`——系统会自动同步**最新业务知识库**，并顺手把 **OpenMotion 及已装相关插件升级到最新稳定版**。
- **管理员维护知识库**：
  - 修改 `knowledge/` 中对应的 Markdown 文件，递增 `SKILL.md` 中的 `version`，执行 `git commit && git push` 即可全员可拉取。
  - 新增知识文件时，记得同步登记到 `SKILL.md` 第一节的知识库优先级清单与上面的目录结构。

---

## 四、出片卡住了？先看这份

| 现象 | 去哪查 |
|---|---|
| OpenMotion 装好了但导不出 MP4、组件一直「下载中」 | `knowledge/06-rendering-playbook.md` 第一、二节 |
| `EXPORT_WORKER_INTERRUPTED`、渲染没反应 | 同上，第三节（改用前台同步渲染） |
| lint 报中文字体 / 顶层 clip 错误 | 同上，第三节 3.2 |
| 成片文字乱码、结尾出现全屏尾卡、封面字被挤 | 同上，第四节抽帧质检清单 |
| 安装失败后的正确兜底姿势 | `knowledge/00-auto-setup.md` 第三节 |

非技术同事不用自己查——直接把现象告诉 WorkBuddy，Agent 会按手册自动处理。
