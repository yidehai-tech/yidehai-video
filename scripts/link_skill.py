#!/usr/bin/env python3
"""
亿德海 Skill 跨宿主一键桥接挂载工具（跨平台 macOS / Linux / Windows，纯标准库）

解决多 AI Agent 工具共存时的「Skill 目录孤岛」问题：
  - 将当前 yidehai-video-skill 目录通过软链（macOS/Linux）或目录联接 mklink /J（Windows）
    挂载到本机已安装的各家 Agent 技能目录，始终保持单一事实源，更新一次全工具同步；
  - 可选针对指定业务项目目录（--project-dir），自动挂载项目级 `.agents/skills/` 与 `.skills/`，
    并在项目根目录安全写入/追加标准 `AGENTS.md` 兜底触发规则（不覆盖原有内容）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "yidehai-video-skill"
SKILL_ROOT = Path(__file__).resolve().parent.parent

KNOWN_HOST_SKILL_DIRS = [
    ("agents-standard", Path.home() / ".agents" / "skills"),
    ("workbuddy", Path.home() / ".workbuddy" / "skills"),
    ("claude", Path.home() / ".claude" / "skills"),
    ("codex", Path.home() / ".codex" / "skills"),
    ("gemini", Path.home() / ".gemini" / "skills"),
    ("cursor", Path.home() / ".cursor" / "skills"),
]

AGENTS_MD_MARKER = "<!-- yidehai-video-skill:auto-routing -->"

AGENTS_MD_BLOCK = f"""
{AGENTS_MD_MARKER}
## 亿德海短视频与图文生产规范（跨 Agent 通用兜底入口）

本项目所有旧衣回收相关的短视频、大字报、动效片、图文故事片、小红书轮播图、即梦/Flow AI 视频与口播包装任务，开工前**必须先读取并严格遵循** `yidehai-video-skill/SKILL.md`（优先查找当前项目 `.agents/skills/yidehai-video-skill/SKILL.md` 或 `.skills/yidehai-video-skill/SKILL.md`）：

1. 严守 `knowledge/01-brand-rules.md` 合规硬红线（0 禁用词、无底部品牌浮条、无全屏静态尾卡）；
2. **严禁未经用户明确选择静默扣积分调用宿主内置生图/生视频、即梦 CLI 或 Google Flow**；
3. 首次开工未配置本地素材路径时，先引导配置并持久化到 `~/.yidehai-video/config.json`。
"""


def _is_same_target(link_path: Path, source: Path) -> bool:
    try:
        return link_path.resolve() == source.resolve()
    except Exception:
        return False


def create_dir_link(source: Path, dest: Path, dry_run: bool = False) -> dict:
    source = source.resolve()
    if dest.exists() or dest.is_symlink():
        if _is_same_target(dest, source):
            return {"target": str(dest), "status": "already_linked"}
        return {
            "target": str(dest),
            "status": "skipped_exists",
            "reason": "目标路径已存在且指向不同目录，为安全起见未覆盖。",
        }

    if dry_run:
        return {"target": str(dest), "status": "would_link", "source": str(source)}

    dest.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        # 使用目录联接（Junction），在 Windows 上无需管理员权限即可生效
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dest), str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return {
                "target": str(dest),
                "status": "failed",
                "error": (proc.stderr or proc.stdout).strip(),
            }
    else:
        os.symlink(str(source), str(dest), target_is_directory=True)
    return {"target": str(dest), "status": "linked", "source": str(source)}


def ensure_project_agents_md(project_dir: Path, dry_run: bool = False) -> dict:
    agents_md = project_dir / "AGENTS.md"
    if agents_md.exists():
        content = agents_md.read_text(encoding="utf-8")
        if AGENTS_MD_MARKER in content or SKILL_NAME in content:
            return {"file": str(agents_md), "status": "already_configured"}
        if dry_run:
            return {"file": str(agents_md), "status": "would_append"}
        agents_md.write_text(content.rstrip() + "\n" + AGENTS_MD_BLOCK.lstrip(), encoding="utf-8")
        return {"file": str(agents_md), "status": "appended"}

    if dry_run:
        return {"file": str(agents_md), "status": "would_create"}
    agents_md.write_text("# 项目 Agent 协作规范\n" + AGENTS_MD_BLOCK, encoding="utf-8")
    return {"file": str(agents_md), "status": "created"}


def main() -> None:
    parser = argparse.ArgumentParser(description="将 yidehai-video-skill 跨宿主软链/联接到本机各 Agent 与项目目录")
    parser.add_argument("--project-dir", default="", help="可选：目标业务项目目录（挂载 .agents/skills 与 .skills 并写入 AGENTS.md）")
    parser.add_argument("--extra-skills-dir", action="append", default=[], help="可选：额外宿主 skills 根目录（如豆包内置 .skills 目录，可重复传参）")
    parser.add_argument("--skip-user-hosts", action="store_true", help="跳过用户级宿主目录（仅挂载 --project-dir / --extra-skills-dir）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览将要执行的挂载操作，不实际修改文件系统")
    args = parser.parse_args()

    results: dict = {
        "ok": True,
        "skill_source": str(SKILL_ROOT),
        "user_hosts": [],
        "extra_dirs": [],
        "project": {},
    }

    if not args.skip_user_hosts:
        for host_name, skills_dir in KNOWN_HOST_SKILL_DIRS:
            # 仅对已安装（父目录存在）的宿主或标准 ~/.agents 创建挂载，避免制造垃圾隐藏目录
            if host_name == "agents-standard" or skills_dir.parent.exists():
                res = create_dir_link(SKILL_ROOT, skills_dir / SKILL_NAME, dry_run=args.dry_run)
                results["user_hosts"].append({"host": host_name, **res})

    for extra in args.extra_skills_dir:
        extra_root = Path(extra).expanduser().resolve()
        res = create_dir_link(SKILL_ROOT, extra_root / SKILL_NAME, dry_run=args.dry_run)
        results["extra_dirs"].append(res)

    if args.project_dir:
        proj = Path(args.project_dir).expanduser().resolve()
        if not proj.is_dir():
            raise FileNotFoundError(f"目标项目目录不存在：{proj}")
        results["project"]["agents_skills"] = create_dir_link(
            SKILL_ROOT, proj / ".agents" / "skills" / SKILL_NAME, dry_run=args.dry_run
        )
        results["project"]["dot_skills"] = create_dir_link(
            SKILL_ROOT, proj / ".skills" / SKILL_NAME, dry_run=args.dry_run
        )
        results["project"]["agents_md"] = ensure_project_agents_md(proj, dry_run=args.dry_run)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
