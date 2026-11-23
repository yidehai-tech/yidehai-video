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
├── SKILL.md                    # 核心工作流与自检规则（v1.1.0）
├── README.md                   # 本使用与更新说明
└── knowledge/
    ├── 00-auto-setup.md        # 自动环境检测与 OpenMotion / 配音依赖一键安装手册
    ├── 01-brand-rules.md       # 短视频合规硬红线 + 方案A收尾规范（最高优先级）
    ├── 02-business-faq.md      # 真实业务规则（起收标准/品类/流程，对外脱敏版）
    ├── 03-copy-formula.md      # 写稿方法论（第零步切角/获客4.0/感觉词/字数）
    ├── 04-visual-style.md      # 竖屏视觉规范 + OpenMotion 动效与双封面约束
    └── 05-good-examples.md     # 5 条已验证的过审样本
```

---

## 三、线上安装与团队一键更新

线上公开仓库：`https://github.com/yidehai-tech/yidehai-video-skill`

- **同事首次安装**：
  - 在 WorkBuddy 中直接发一句：`请从 https://github.com/yidehai-tech/yidehai-video-skill 安装 yidehai-video-skill`
  - 或在支持 `skills` CLI 的环境中执行：`npx skills add yidehai-tech/yidehai-video-skill`
- **同事一键更新**：
  - 群里通知更新后，在 WorkBuddy 中直接说：`帮我更新一下 yidehai-video-skill`（或重新运行安装命令覆盖更新）。
- **管理员维护知识库**：
  - 修改 `knowledge/` 中对应的 Markdown 文件，递增 `SKILL.md` 中的 `version`，执行 `git commit && git push` 即可全员可拉取。
