#!/usr/bin/env python3
"""
亿德海 Skill 跨宿主一键挂载与同步工具（跨平台 macOS / Linux / Windows，纯标准库）

解决多 AI Agent 工具共存时的「Skill 目录孤岛」与「Windows 宿主清理连坐真源」问题：
  - macOS / Linux（默认 symlink）：创建软链指向独立真源，更新一次全工具同步；
  - Windows（默认 copy 安全镜像副本）：排除 .git 复制到目标宿主技能目录并写入 .yidehai-skill-sync.json，
    彻底防止豆包 / WorkBuddy 等 Windows 宿主同步清理技能目录时穿透 Junction 误删真源；
    再次运行本脚本即可一键从真源安全覆盖同步，无需额外恢复脚本；
  - 可选针对指定业务项目目录（--project-dir），自动挂载项目级 `.agents/skills/` 与 `.skills/`，
    并在项目根目录安全写入/追加标准 `AGENTS.md` 兜底触发规则（不覆盖原有内容）。
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

SKILL_NAME = "yidehai-video-skill"
SKILL_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = Path.home() / ".yidehai-video"
APP_BIN_DIR = APP_DIR / "bin"
SYNC_MARKER_NAME = ".yidehai-skill-sync.json"
COPY_IGNORE_NAMES = {".git", "__pycache__", ".DS_Store", ".pytest_cache"}
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

KNOWN_HOST_SKILL_DIRS = [
    ("agents-standard", Path.home() / ".agents" / "skills"),
    ("workbuddy", Path.home() / ".workbuddy" / "skills"),
    ("openclaw", Path.home() / ".openclaw" / "skills"),
    ("doubao", Path.home() / ".doubao" / "skills"),
    ("qwen", Path.home() / ".qwen" / "skills"),
    ("claude", Path.home() / ".claude" / "skills"),
    ("codex", Path.home() / ".codex" / "skills"),
    ("gemini", Path.home() / ".gemini" / "skills"),
    ("cursor", Path.home() / ".cursor" / "skills"),
    ("trae", Path.home() / ".trae" / "skills"),
    ("windsurf", Path.home() / ".windsurf" / "skills"),
    ("windsurf-codeium", Path.home() / ".codeium" / "windsurf" / "skills"),
    ("qoder", Path.home() / ".qoder" / "skills"),
    ("kiro", Path.home() / ".kiro" / "skills"),
    ("cline", Path.home() / ".cline" / "skills"),
    ("roo", Path.home() / ".roo" / "skills"),
    ("copilot", Path.home() / ".copilot" / "skills"),
    ("opencode", Path.home() / ".opencode" / "skills"),
]

AGENTS_MD_MARKER = "<!-- yidehai-video-skill:auto-routing -->"

AGENTS_MD_BLOCK = f"""
{AGENTS_MD_MARKER}
## 亿德海短视频与图文生产规范（跨 Agent 通用兜底入口）

本项目所有旧衣回收相关的短视频、大字报、动效片、图文故事片、小红书轮播图、即梦/Flow AI 视频与口播包装任务，开工前**必须先读取并严格遵循** `yidehai-video-skill/SKILL.md`（优先查找当前项目 `.agents/skills/yidehai-video-skill/SKILL.md` 或 `.skills/yidehai-video-skill/SKILL.md`）：

1. 严守 `knowledge/01-brand-rules.md` 合规硬红线（0 禁用词、无底部品牌浮条、无全屏静态尾卡）；
2. **严禁未经用户明确选择静默扣积分调用宿主内置生图/生视频、即梦 CLI 或 Google Flow**；
3. **生成前硬门禁（严禁出残缺半成品）**：每次出片前必须先执行 `python3 <skill_dir>/scripts/media_manager.py preflight --track <轨道>`；缺背景视频源/音乐源/图源 Key 或素材目录时必须先让用户补齐并持久化到 `~/.yidehai-video/config.json`，严禁跳过回落纯色底或无声失败作品；
4. **Agent 自动自愈挂载（绝不让用户手动敲命令）**：如果你是首次打开本项目、且发现 `yidehai-video-skill` 尚未出现在你自己的原生技能清单里，请立刻主动确认你自身的技能根目录并自动执行一次 `python3 <skill_dir>/scripts/link_skill.py --skip-user-hosts --extra-skills-dir "<你的技能根目录>"` 完成静默挂载（Windows 默认安全镜像复制，防宿主清理误删真源），不要把命令甩给用户自己跑。
"""


def _is_same_target(link_path: Path, source: Path) -> bool:
    try:
        return link_path.resolve() == source.resolve()
    except Exception:
        return False


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    if sys.platform.startswith("win") and hasattr(os.path, "isjunction"):
        try:
            return bool(os.path.isjunction(path))
        except Exception:
            return False
    return False


def _safe_remove_link_only(path: Path) -> None:
    """安全移除软链或 Windows Junction 本身，绝不递归删除其指向的源目录内容。"""
    if path.is_symlink():
        path.unlink()
    elif sys.platform.startswith("win") and hasattr(os.path, "isjunction") and os.path.isjunction(path):
        os.rmdir(path)


def _sync_copy_dir(source: Path, dest: Path, force_sync: bool = False, dry_run: bool = False) -> dict:
    source = source.resolve()
    if dest.exists() or _is_reparse_or_symlink(dest):
        # 防止自己复制到自己
        if not _is_reparse_or_symlink(dest) and _is_same_target(dest, source):
            return {"target": str(dest), "status": "already_source", "mode": "copy"}

        # 若目标原本是指向真源的旧 symlink / Windows Junction，允许安全迁移为独立副本
        if _is_reparse_or_symlink(dest) and _is_same_target(dest, source):
            if dry_run:
                return {"target": str(dest), "status": "would_migrate_link_to_copy", "mode": "copy", "source": str(source)}
            _safe_remove_link_only(dest)
        elif dest.is_dir() and ((dest / SYNC_MARKER_NAME).exists() or force_sync):
            if dry_run:
                return {"target": str(dest), "status": "would_sync_copy", "mode": "copy", "source": str(source)}
            shutil.rmtree(dest)
        else:
            return {
                "target": str(dest),
                "status": "skipped_exists",
                "mode": "copy",
                "reason": "目标路径已存在且非本脚本托管副本，为安全起见未覆盖（如确认覆盖可加 --force-sync）。",
            }
    elif dry_run:
        return {"target": str(dest), "status": "would_copy", "mode": "copy", "source": str(source)}

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        dest,
        ignore=shutil.ignore_patterns(*COPY_IGNORE_NAMES),
    )
    marker = {
        "managed_by": "yidehai-video-skill/scripts/link_skill.py",
        "source": str(source),
        "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (dest / SYNC_MARKER_NAME).write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"target": str(dest), "status": "copied", "mode": "copy", "source": str(source)}


def install_skill_target(
    source: Path,
    dest: Path,
    mode: str = "auto",
    force_sync: bool = False,
    dry_run: bool = False,
) -> dict:
    resolved_mode = mode
    if resolved_mode == "auto":
        # Windows 宿主清理 .skills 目录时可能递归穿透 Junction 误删真源，因此默认使用安全镜像副本
        resolved_mode = "copy" if sys.platform.startswith("win") else "symlink"

    if resolved_mode == "copy":
        return _sync_copy_dir(source, dest, force_sync=force_sync, dry_run=dry_run)

    source = source.resolve()
    if dest.exists() or _is_reparse_or_symlink(dest):
        if _is_same_target(dest, source):
            return {"target": str(dest), "status": "already_linked", "mode": resolved_mode}
        return {
            "target": str(dest),
            "status": "skipped_exists",
            "mode": resolved_mode,
            "reason": "目标路径已存在且指向不同目录，为安全起见未覆盖。",
        }

    if dry_run:
        return {"target": str(dest), "status": "would_link", "mode": resolved_mode, "source": str(source)}

    dest.parent.mkdir(parents=True, exist_ok=True)
    if resolved_mode == "junction" or sys.platform.startswith("win"):
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
                "mode": "junction",
                "error": (proc.stderr or proc.stdout).strip(),
            }
        return {"target": str(dest), "status": "linked", "mode": "junction", "source": str(source)}

    os.symlink(str(source), str(dest), target_is_directory=True)
    return {"target": str(dest), "status": "linked", "mode": "symlink", "source": str(source)}


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


def _find_ffmpeg_pair() -> tuple[str | None, str | None]:
    """检测本机或 ~/.yidehai-video/bin 是否已具备可用的 ffmpeg / ffprobe。"""
    is_win = sys.platform.startswith("win")
    ff_name = "ffmpeg.exe" if is_win else "ffmpeg"
    fp_name = "ffprobe.exe" if is_win else "ffprobe"

    def _find(name: str, bare: str) -> str | None:
        local_cand = APP_BIN_DIR / name
        if local_cand.is_file():
            return str(local_cand)
        w = shutil.which(name) or shutil.which(bare)
        if w and (not is_win or w.lower().endswith(".exe")):
            return w
        return None

    return _find(ff_name, "ffmpeg"), _find(fp_name, "ffprobe")


def _install_win_ffmpeg_to_app_bin() -> tuple[bool, str]:
    """Windows 下优先 winget，其次直拉静态包将 ffmpeg.exe / ffprobe.exe 放入 ~/.yidehai-video/bin。"""
    APP_BIN_DIR.mkdir(parents=True, exist_ok=True)
    if shutil.which("winget"):
        proc = subprocess.run(
            [
                "winget", "install", "-e", "--id", "Gyan.FFmpeg",
                "--accept-source-agreements", "--accept-package-agreements", "--silent",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        # winget 刚装完当前进程 PATH 可能未刷新，主动扫描 WinGet 安装目录拷贝到 ~/.yidehai-video/bin 立即可用
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            winget_pkgs = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.is_dir():
                for ff in winget_pkgs.rglob("ffmpeg.exe"):
                    fp = ff.parent / "ffprobe.exe"
                    if fp.is_file():
                        shutil.copy2(ff, APP_BIN_DIR / "ffmpeg.exe")
                        shutil.copy2(fp, APP_BIN_DIR / "ffprobe.exe")
                        return True, "installed_via_winget"
        ff, fp = _find_ffmpeg_pair()
        if ff and fp:
            return True, "installed_via_winget"
        _ = proc

    # 兜底：经国内镜像直接拉取 BtbN Windows 静态编译包并解压提取 ffmpeg.exe / ffprobe.exe
    raw_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    urls = [f"https://gh-proxy.com/{raw_url}", f"https://ghfast.top/{raw_url}", raw_url]
    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "ffmpeg.zip"
        downloaded = False
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (yidehai-video-skill/2.6)"})
                with urllib.request.urlopen(req, timeout=90) as resp, open(zip_path, "wb") as f:
                    while True:
                        chunk = resp.read(131072)
                        if not chunk:
                            break
                        f.write(chunk)
                if zip_path.stat().st_size > 1_000_000:
                    downloaded = True
                    break
            except Exception:
                zip_path.unlink(missing_ok=True)
                continue
        if not downloaded:
            return False, "download_failed"
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                found_ff = found_fp = False
                for member in zf.namelist():
                    low = member.lower()
                    if low.endswith("/bin/ffmpeg.exe"):
                        with zf.open(member) as src, open(APP_BIN_DIR / "ffmpeg.exe", "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        found_ff = True
                    elif low.endswith("/bin/ffprobe.exe"):
                        with zf.open(member) as src, open(APP_BIN_DIR / "ffprobe.exe", "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        found_fp = True
                if found_ff and found_fp:
                    return True, "installed_via_static_zip"
        except Exception as exc:
            return False, f"extract_failed:{exc}"
    return False, "ffmpeg_not_found_in_archive"


def ensure_core_dependencies(dry_run: bool = False) -> dict:
    """安装阶段一次性补齐视频生产必备的免费基础依赖（Pillow、edge-tts、ffmpeg/ffprobe），避免二次确认。"""
    report: dict = {"python_packages": {}, "ffmpeg": {}}

    # 1) Python 必备包：Pillow（大字报/封面排版）、edge-tts（中文 AI 旁白）
    pkg_specs = [("Pillow", "PIL"), ("edge-tts", "edge_tts")]
    missing_pkgs = [pip_name for pip_name, mod_name in pkg_specs if importlib.util.find_spec(mod_name) is None]
    for pip_name, mod_name in pkg_specs:
        if importlib.util.find_spec(mod_name) is not None:
            report["python_packages"][pip_name] = "already_installed"
    if missing_pkgs:
        if dry_run:
            for p in missing_pkgs:
                report["python_packages"][p] = "would_install"
        else:
            cmd = [sys.executable, "-m", "pip", "install", "-i", PYPI_MIRROR, "--quiet", *missing_pkgs]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if proc.returncode == 0:
                for p in missing_pkgs:
                    report["python_packages"][p] = "installed"
            else:
                # 若全局 pip 受限，自动回退 --user
                proc2 = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--user", "-i", PYPI_MIRROR, "--quiet", *missing_pkgs],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                for p in missing_pkgs:
                    report["python_packages"][p] = "installed_user" if proc2.returncode == 0 else f"failed:{(proc2.stderr or proc.stderr).strip()[-200:]}"

    # 2) ffmpeg / ffprobe
    ff, fp = _find_ffmpeg_pair()
    if ff and fp:
        report["ffmpeg"] = {"status": "already_installed", "ffmpeg": ff, "ffprobe": fp}
    elif dry_run:
        report["ffmpeg"] = {"status": "would_install"}
    else:
        if sys.platform.startswith("win"):
            ok, detail = _install_win_ffmpeg_to_app_bin()
            ff2, fp2 = _find_ffmpeg_pair()
            report["ffmpeg"] = {"status": detail if ok else f"failed:{detail}", "ffmpeg": ff2, "ffprobe": fp2}
        elif sys.platform == "darwin" and shutil.which("brew"):
            proc = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            ff2, fp2 = _find_ffmpeg_pair()
            report["ffmpeg"] = {
                "status": "installed_via_brew" if (proc.returncode == 0 and ff2 and fp2) else f"failed:{proc.stderr.strip()[-200:]}",
                "ffmpeg": ff2,
                "ffprobe": fp2,
            }
        else:
            report["ffmpeg"] = {"status": "manual_required", "hint": "请使用系统包管理器安装 ffmpeg（含 ffprobe）。"}

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="将 yidehai-video-skill 跨宿主挂载/同步到本机各 Agent 与项目目录")
    parser.add_argument("--project-dir", default="", help="可选：目标业务项目目录（挂载 .agents/skills 与 .skills 并写入 AGENTS.md）")
    parser.add_argument("--extra-skills-dir", action="append", default=[], help="可选：额外宿主 skills 根目录（如豆包内置 .skills 目录，可重复传参）")
    parser.add_argument("--skip-user-hosts", action="store_true", help="跳过用户级宿主目录（仅挂载 --project-dir / --extra-skills-dir）")
    parser.add_argument(
        "--mode",
        choices=["auto", "copy", "symlink", "junction"],
        default="auto",
        help="挂载模式：auto（macOS/Linux 软链，Windows 安全镜像复制防宿主清理穿透删真源）、copy、symlink、junction",
    )
    parser.add_argument("--force-sync", action="store_true", help="copy 模式下若目标目录已存在但非托管副本，允许强制覆盖同步")
    parser.add_argument("--skip-deps", action="store_true", help="跳过基础免费依赖（ffmpeg / edge-tts / Pillow）自动检测与安装")
    parser.add_argument("--dry-run", action="store_true", help="仅预览将要执行的挂载操作，不实际修改文件系统")
    args = parser.parse_args()

    effective_mode = args.mode if args.mode != "auto" else ("copy" if sys.platform.startswith("win") else "symlink")
    results: dict = {
        "ok": True,
        "skill_source": str(SKILL_ROOT),
        "mode": effective_mode,
        "user_hosts": [],
        "extra_dirs": [],
        "project": {},
        "dependencies": {},
    }

    # 避坑检测：若真源位于单一宿主私有管理目录（如 .workbuddy/skills），存在被宿主自动回收/清空风险
    src_str = str(SKILL_ROOT).replace("\\", "/").lower()
    managed_markers = ("/.workbuddy/skills/", "/.doubao/skills/", "/.claude/skills/", "/.codex/skills/")
    if any(m in src_str for m in managed_markers):
        results["warning"] = (
            "检测到当前 Skill 真源位于某个单一 Agent 的私有管理目录内，部分宿主会在同步/重启时清理该目录导致文件丢失。"
            "强烈建议将仓库克隆到独立持久化目录（例如 ~/.yidehai-video/skill-repo 或业务盘独立目录），再从独立目录运行 link_skill.py 向各宿主同步。"
        )

    if not args.skip_user_hosts:
        for host_name, skills_dir in KNOWN_HOST_SKILL_DIRS:
            # 仅对已安装（父目录存在）的宿主或标准 ~/.agents 创建挂载，避免制造垃圾隐藏目录
            if host_name == "agents-standard" or skills_dir.parent.exists():
                res = install_skill_target(
                    SKILL_ROOT,
                    skills_dir / SKILL_NAME,
                    mode=args.mode,
                    force_sync=args.force_sync,
                    dry_run=args.dry_run,
                )
                results["user_hosts"].append({"host": host_name, **res})

    for extra in args.extra_skills_dir:
        extra_root = Path(extra).expanduser().resolve()
        res = install_skill_target(
            SKILL_ROOT,
            extra_root / SKILL_NAME,
            mode=args.mode,
            force_sync=args.force_sync,
            dry_run=args.dry_run,
        )
        results["extra_dirs"].append(res)

    if args.project_dir:
        proj = Path(args.project_dir).expanduser().resolve()
        if not proj.is_dir():
            raise FileNotFoundError(f"目标项目目录不存在：{proj}")
        results["project"]["agents_skills"] = install_skill_target(
            SKILL_ROOT,
            proj / ".agents" / "skills" / SKILL_NAME,
            mode=args.mode,
            force_sync=args.force_sync,
            dry_run=args.dry_run,
        )
        results["project"]["dot_skills"] = install_skill_target(
            SKILL_ROOT,
            proj / ".skills" / SKILL_NAME,
            mode=args.mode,
            force_sync=args.force_sync,
            dry_run=args.dry_run,
        )
        results["project"]["agents_md"] = ensure_project_agents_md(proj, dry_run=args.dry_run)

    if not args.skip_deps:
        results["dependencies"] = ensure_core_dependencies(dry_run=args.dry_run)

    results["agent_self_heal_hint"] = (
        "若当前 Agent 自身的技能根目录不在上述 user_hosts 列表中，请 Agent 主动查找自身技能目录并自动执行："
        "python3 scripts/link_skill.py --skip-user-hosts --extra-skills-dir \"<你的技能根目录>\"，"
        "切勿让用户手动敲命令。Windows 下默认采用安全镜像复制，更新真源后重跑本脚本即可一键同步。"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
