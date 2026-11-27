#!/usr/bin/env python3
"""
兼容过渡脚本（已在 v3.0.0 废弃全局 Skill 挂载模式）

从 v3.0.0 起，`yidehai-video` 已转型为独立项目级工作台：
  - 所有桌面 AI 工具直接打开本项目文件夹即可通过根目录 `AGENTS.md` / `CLAUDE.md` 自动生效；
  - 不再向各宿主私有 `.skills` 目录复制或创建全局软链。
本脚本保留原有 CLI 参数避免旧指令报错，并自动委托给 `scripts/setup_project.py` 完成初始化与旧配置平滑迁移。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import setup_project  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="[已废弃] v3.0.0 已转为项目级工作台，本脚本自动委托给 setup_project.py 执行初始化与旧配置迁移"
    )
    parser.add_argument("--project-dir", default="", help="[兼容保留] 旧版参数，已忽略")
    parser.add_argument("--extra-skills-dir", action="append", default=[], help="[兼容保留] 转为传给旧全局 Skill 扫描")
    parser.add_argument("--skip-user-hosts", action="store_true", help="[兼容保留] 已忽略")
    parser.add_argument("--mode", choices=["auto", "copy", "symlink", "junction"], default="auto", help="[兼容保留] 已忽略")
    parser.add_argument("--force-sync", action="store_true", help="[兼容保留] 已忽略")
    parser.add_argument("--skip-deps", action="store_true", help="跳过基础免费依赖检测与安装")
    parser.add_argument("--dry-run", action="store_true", help="仅预览操作，不实际修改文件系统")
    args = parser.parse_args()

    setup_res = setup_project.run_setup(
        skip_deps=args.skip_deps,
        dry_run=args.dry_run,
        cleanup_legacy_skills=False,
        extra_skills_dirs=args.extra_skills_dir,
    )
    output = {
        "ok": True,
        "deprecated": True,
        "notice": (
            "提示：yidehai-video v3.0.0 已转为独立项目级工作台，不再挂载全局 Skill。"
            "团队成员只需在任意桌面 AI 工具中打开本项目文件夹即可直接出片。"
            "如需清理旧版全局 Skill 挂载残留，请运行：python3 scripts/setup_project.py --cleanup-legacy-skills"
        ),
        "setup": setup_res,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
