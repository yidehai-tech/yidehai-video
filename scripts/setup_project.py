#!/usr/bin/env python3
"""
亿德海短视频工作台（项目级 v3.0.0）一键初始化、旧版平滑迁移与依赖补齐脚本（纯标准库，跨平台 macOS / Linux / Windows）

功能：
  1. 初始化当前项目本地数据目录 `.yidehai/` 与成片输出目录 `outputs/`；
  2. 自动、无损、幂等地将旧版全局 `~/.yidehai-video/` 的配置、API Key、防重账本、任务台账、缓存与 FFmpeg 迁移至 `.yidehai/`（原目录完整保留作备份）；
  3. 若已有历史任务，自动生成或刷新可见仪表盘 `outputs/dashboard.html`；
  4. 一键补齐基础免费依赖（Pillow、edge-tts、ffmpeg/ffprobe）；
  5. 扫描并（在传 `--cleanup-legacy-skills` 时）安全清理旧版全局 Skill 软链/托管副本。
"""

from __future__ import annotations

import argparse
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
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import media_manager  # noqa: E402
import task_tracker  # noqa: E402

LEGACY_SKILL_NAMES = ("yidehai-video", "yidehai-video-skill")
SYNC_MARKER_NAME = ".yidehai-skill-sync.json"
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


def _is_same_target(path_a: Path, path_b: Path) -> bool:
    try:
        return path_a.resolve() == path_b.resolve()
    except Exception:
        return False


def _is_junction(path: Path) -> bool:
    if sys.platform.startswith("win") and hasattr(os.path, "isjunction"):
        try:
            return bool(os.path.isjunction(path))
        except Exception:
            return False
    return False


def _is_reparse_or_symlink(path: Path) -> bool:
    return path.is_symlink() or _is_junction(path)


def _safe_remove_link_only(path: Path) -> None:
    """仅移除软链或 Windows Junction 本身，绝不递归删除其指向的源目录内容。"""
    if path.is_symlink():
        path.unlink()
    elif _is_junction(path):
        os.rmdir(path)


def _find_ffmpeg_pair() -> tuple[str | None, str | None]:
    """检测本机、项目 `.yidehai/bin` 或旧版 `~/.yidehai-video/bin` 是否已具备可用的 ffmpeg / ffprobe。"""
    is_win = sys.platform.startswith("win")
    ff_name = "ffmpeg.exe" if is_win else "ffmpeg"
    fp_name = "ffprobe.exe" if is_win else "ffprobe"
    bin_dirs = [media_manager.APP_DIR / "bin", media_manager.LEGACY_APP_DIR / "bin"]

    def _find(name: str, bare: str) -> str | None:
        for d in bin_dirs:
            cand = d / name
            if cand.is_file():
                return str(cand)
        w = shutil.which(name) or shutil.which(bare)
        if w and (not is_win or w.lower().endswith(".exe")):
            return w
        return None

    return _find(ff_name, "ffmpeg"), _find(fp_name, "ffprobe")


def _install_win_ffmpeg_to_app_bin() -> tuple[bool, str]:
    """Windows 下优先 winget，其次直拉静态包将 ffmpeg.exe / ffprobe.exe 放入项目 `.yidehai/bin`。"""
    app_bin_dir = media_manager.APP_DIR / "bin"
    app_bin_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("winget"):
        subprocess.run(
            [
                "winget", "install", "-e", "--id", "Gyan.FFmpeg",
                "--accept-source-agreements", "--accept-package-agreements", "--silent",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            winget_pkgs = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.is_dir():
                for ff in winget_pkgs.rglob("ffmpeg.exe"):
                    fp = ff.parent / "ffprobe.exe"
                    if fp.is_file():
                        shutil.copy2(ff, app_bin_dir / "ffmpeg.exe")
                        shutil.copy2(fp, app_bin_dir / "ffprobe.exe")
                        return True, "installed_via_winget"
        ff, fp = _find_ffmpeg_pair()
        if ff and fp:
            return True, "installed_via_winget"

    raw_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    urls = [f"https://gh-proxy.com/{raw_url}", f"https://ghfast.top/{raw_url}", raw_url]
    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "ffmpeg.zip"
        downloaded = False
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (yidehai-video/3.0)"})
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
                        with zf.open(member) as src, open(app_bin_dir / "ffmpeg.exe", "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        found_ff = True
                    elif low.endswith("/bin/ffprobe.exe"):
                        with zf.open(member) as src, open(app_bin_dir / "ffprobe.exe", "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        found_fp = True
                if found_ff and found_fp:
                    return True, "installed_via_static_zip"
        except Exception as exc:
            return False, f"extract_failed:{exc}"
    return False, "ffmpeg_not_found_in_archive"


def ensure_core_dependencies(dry_run: bool = False) -> dict[str, Any]:
    """初始化阶段一次性补齐视频生产必备的免费基础依赖（Pillow、edge-tts、ffmpeg/ffprobe）。"""
    report: dict[str, Any] = {"python_packages": {}, "ffmpeg": {}}

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
                proc2 = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--user", "-i", PYPI_MIRROR, "--quiet", *missing_pkgs],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                for p in missing_pkgs:
                    report["python_packages"][p] = (
                        "installed_user"
                        if proc2.returncode == 0
                        else f"failed:{(proc2.stderr or proc.stderr).strip()[-200:]}"
                    )

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


def handle_legacy_global_skills(
    cleanup: bool = False,
    dry_run: bool = False,
    extra_skills_dirs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """扫描旧版全局 Skill 挂载残留；仅在显式开启 cleanup 时安全移除软链/Junction/托管副本。"""
    scan_roots: list[tuple[str, Path]] = list(KNOWN_HOST_SKILL_DIRS)
    for idx, extra in enumerate(extra_skills_dirs or []):
        if extra and str(extra).strip():
            scan_roots.append((f"extra-{idx + 1}", Path(extra).expanduser()))

    seen_paths: set[str] = set()
    findings: list[dict[str, Any]] = []
    for host_name, skills_dir in scan_roots:
        for skill_name in LEGACY_SKILL_NAMES:
            cand = skills_dir / skill_name
            cand_key = str(cand)
            if cand_key in seen_paths:
                continue
            seen_paths.add(cand_key)
            if not (cand.exists() or _is_reparse_or_symlink(cand)):
                continue

            # 严禁误删当前项目目录本身
            if not _is_reparse_or_symlink(cand) and _is_same_target(cand, PROJECT_ROOT):
                findings.append({
                    "host": host_name,
                    "path": str(cand),
                    "kind": "project_root",
                    "removable": False,
                    "action": "skipped_project_root",
                })
                continue

            if cand.is_symlink():
                kind = "symlink"
            elif _is_junction(cand):
                kind = "junction"
            elif cand.is_dir() and (cand / SYNC_MARKER_NAME).exists():
                kind = "managed_copy"
            else:
                kind = "unmanaged"

            removable = kind in {"symlink", "junction", "managed_copy"}
            action = "found"
            if cleanup:
                if not removable:
                    action = "skipped_unmanaged"
                elif dry_run:
                    action = "would_remove"
                else:
                    if kind in {"symlink", "junction"}:
                        _safe_remove_link_only(cand)
                    else:
                        shutil.rmtree(cand)
                    action = "removed"

            findings.append({
                "host": host_name,
                "path": str(cand),
                "kind": kind,
                "removable": removable,
                "action": action,
            })
    return findings


def run_setup(
    skip_deps: bool = False,
    skip_migrate: bool = False,
    cleanup_legacy_skills: bool = False,
    dry_run: bool = False,
    extra_skills_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """执行项目级工作台一站式初始化与平滑迁移。"""
    if not dry_run:
        media_manager.APP_DIR.mkdir(parents=True, exist_ok=True)
        media_manager.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    migration_res: dict[str, Any]
    if skip_migrate:
        migration_res = {"ok": True, "status": "skipped"}
    else:
        migration_res = media_manager.migrate_legacy_state(force_merge=True, dry_run=dry_run)

    dashboard_rebuilt = False
    if not dry_run and task_tracker.TASKS_PATH.exists():
        try:
            with media_manager.file_lock(task_tracker.LOCK_PATH, timeout=10.0):
                tdata = task_tracker._load_unlocked()
                task_tracker._heal_stale_running(tdata)
                task_tracker._save_unlocked(tdata)
            dashboard_rebuilt = task_tracker.DASHBOARD_PATH.exists()
        except Exception:
            dashboard_rebuilt = False

    deps_res: dict[str, Any] = (
        {"skipped": True} if skip_deps else ensure_core_dependencies(dry_run=dry_run)
    )
    legacy_skills = handle_legacy_global_skills(
        cleanup=cleanup_legacy_skills,
        dry_run=dry_run,
        extra_skills_dirs=extra_skills_dirs,
    )

    return {
        "ok": True,
        "version": "3.0.0",
        "dry_run": dry_run,
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(media_manager.APP_DIR),
        "outputs_dir": str(media_manager.OUTPUTS_DIR),
        "dashboard_path": str(task_tracker.DASHBOARD_PATH),
        "dashboard_rebuilt": dashboard_rebuilt,
        "migration": migration_res,
        "dependencies": deps_res,
        "legacy_global_skills": legacy_skills,
        "next_step_hint": (
            "项目工作台已就绪。非技术同事只需在任意桌面 AI 工具中打开本项目文件夹，"
            "直接发送「帮我做一条换季清衣柜的大字报视频」即可开始出片；"
            "出片前将自动执行 preflight 校验。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海短视频项目级工作台初始化与旧版配置平滑迁移工具")
    parser.add_argument("--cleanup-legacy-skills", action="store_true", help="安全清理旧版全局 Skill 软链或托管副本（不删用户自建目录）")
    parser.add_argument("--extra-skills-dir", action="append", default=[], help="可选：额外扫描/清理的宿主 skills 根目录")
    parser.add_argument("--skip-deps", action="store_true", help="跳过基础免费依赖（Pillow / edge-tts / ffmpeg）检测与安装")
    parser.add_argument("--skip-migrate", action="store_true", help="跳过旧版 ~/.yidehai-video/ 自动迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅预览将要执行的初始化、迁移与清理动作，不修改文件系统")
    args = parser.parse_args()

    res = run_setup(
        skip_deps=args.skip_deps,
        skip_migrate=args.skip_migrate,
        cleanup_legacy_skills=args.cleanup_legacy_skills,
        dry_run=args.dry_run,
        extra_skills_dirs=args.extra_skills_dir,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
