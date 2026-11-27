# Claude Code 项目指南

本项目是**亿德海（yidehai）团队专属的独立项目级短视频生产工作台**（非全局 Skill）。

开始任何操作前，**必须先完整阅读并严格遵守根目录的 `AGENTS.md`**，并按任务需要查阅 `knowledge/00-auto-setup.md` 至 `knowledge/11-local-footage-formats.md`。

核心约定：
- 本地配置、API Key、防重账本、任务台账与下载缓存均位于项目内的 `.yidehai/`（已加入 `.gitignore`，严禁读取明文或提交进 Git）；
- 所有成片产物与可视化的 `dashboard.html` 统一输出到 `outputs/` 目录；
- 首次初始化或成员提到从旧版全局 Skill 迁移时，直接运行 `python3 scripts/setup_project.py`。
