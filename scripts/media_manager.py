#!/usr/bin/env python3
"""
亿德海团队短视频本地配置与在线免版权素材按需管理器（纯标准库，跨平台 macOS / Windows）
- 持久化保存同事本机素材目录与防重账本路径到 ~/.yidehai-video/config.json（绝不提交进 Git）
- 支持双模式在线按需拉取空镜/轻音乐到 ~/.yidehai-video/cache/：
  1) 0 配置直链清单模式（读取 knowledge/media-catalog.json 中的精选免版权或团队共享直链，按需下载）
  2) 可选免费 API 无限扩充模式（配置 Pexels / Pixabay 免费 API Key 后自动按竖屏风景关键词补库）
"""

import argparse
import contextlib
import hashlib
import json
import os
import random
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

FORBIDDEN_TERMS = [
    "顺丰", "京东",
    "当场结算", "当场打款", "当场结钱", "立返", "秒到账", "即时到账", "立刻到账", "马上打钱",
    "微信搜", "搜一搜", "搜微信", "加微信",
    "看主页", "点主页", "点左下角", "点我头像", "点击头像", "点头像",
    "关注我", "评论区扣", "私信我", "私信领",
]


def check_forbidden_terms(texts: list[str]) -> list[str]:
    """统一共享合规硬红线检测，返回命中的禁用词列表。"""
    joined = "\n".join(str(t or "") for t in texts)
    return [term for term in FORBIDDEN_TERMS if term in joined]


def sanitize_slug(raw: str, fallback: str = "video") -> str:
    """跨平台单段安全文件名（剔除路径分隔符、Windows 非法字符与保留名）。"""
    s = str(raw or "").strip()
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", s)
    s = re.sub(r"\.{2,}", ".", s).strip(" .-")
    if not s or s.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        return fallback
    return s[:80]


def safe_child_path(root: Path, *parts: str) -> Path:
    """确保拼接后的路径严格位于 root 目录之内，防止路径穿越。"""
    root_resolved = root.expanduser().resolve()
    target = root_resolved.joinpath(*parts).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"非法输出路径（越出根目录）：{target}") from exc
    return target


def atomic_write_json(path: Path, data: Any) -> None:
    """跨平台原子写入 JSON（临时文件 + os.replace），避免并发或崩溃产生截断文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def file_lock(lock_path: Path, timeout: float = 15.0, stale_seconds: float = 600.0) -> Iterator[None]:
    """基于 O_CREAT|O_EXCL 的跨平台文件锁（支持超时与陈旧锁清理）。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}:{time.time():.0f}\n".encode("utf-8"))
            os.close(fd)
            fd = None
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > stale_seconds:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"获取文件锁超时（可能存在并发任务正在运行）：{lock_path}")
            time.sleep(0.15)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)

APP_DIR = Path.home() / ".yidehai-video"
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_LEDGER_PATH = APP_DIR / "used_history.json"
CACHE_BG_DIR = APP_DIR / "cache" / "bg"
CACHE_BGM_DIR = APP_DIR / "cache" / "bgm"

DEFAULT_SCENIC_QUERIES = [
    "nature forest sunlight",
    "mountain landscape clouds",
    "ocean waves sunset",
    "flowers breeze sky",
    "green leaves wind",
    "meadow sunrise nature",
]

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_PATH = SKILL_ROOT / "knowledge" / "media-catalog.json"


def resolve_ffmpeg_tools() -> tuple[str, str]:
    """跨平台自动定位真正的 ffmpeg / ffprobe 可执行文件（Windows 下严禁误选无扩展名 bash shim）。"""
    is_win = sys.platform.startswith("win")
    ff_name = "ffmpeg.exe" if is_win else "ffmpeg"
    fp_name = "ffprobe.exe" if is_win else "ffprobe"

    search_dirs: list[Path] = [APP_DIR / "bin"]
    om_roots: list[Path] = []
    if os.environ.get("OPENMOTION_HOME"):
        om_roots.append(Path(os.environ["OPENMOTION_HOME"]))
    if os.environ.get("LOCALAPPDATA"):
        om_roots.append(Path(os.environ["LOCALAPPDATA"]) / "openmotion")
    om_roots.extend([
        Path.home() / ".openmotion",
        Path.home() / "Library" / "Application Support" / "openmotion",
        Path.home() / ".local" / "share" / "openmotion",
    ])
    for root in om_roots:
        native = root / "cache" / "native"
        if native.exists():
            for p in native.rglob(ff_name):
                if p.is_file():
                    search_dirs.append(p.parent)

    def _find_one(name: str, bare: str) -> str:
        for d in search_dirs:
            cand = d / name
            if cand.is_file():
                return str(cand)
        w = shutil.which(name) or shutil.which(bare)
        if w:
            if not is_win or w.lower().endswith(".exe"):
                return w
        return name

    return _find_one(ff_name, "ffmpeg"), _find_one(fp_name, "ffprobe")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("local_bg_dirs", [])
    data.setdefault("local_bgm_dirs", [])
    data.setdefault("local_footage_dirs", [])
    data.setdefault("local_motion_templates_dir", "")
    data.setdefault("ledger_path", str(DEFAULT_LEDGER_PATH))
    data.setdefault("cache_bg_dir", str(CACHE_BG_DIR))
    data.setdefault("cache_bgm_dir", str(CACHE_BGM_DIR))
    data.setdefault("bg_source", "both")  # both | local | online
    data.setdefault("initialized", False)
    data.setdefault("onboarding_dismissed", False)
    return data


def save_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def download_file(url: str, dest: Path, timeout: int = 30) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 10_000:
        return True
    tmp = dest.with_suffix(dest.suffix + ".part")

    # 对 GitHub Release 直链自动提供国内镜像兜底，避免国内同事无代理超时
    urls_to_try = [url]
    if url.startswith("https://github.com/"):
        urls_to_try = [
            f"https://gh-proxy.com/{url}",
            f"https://ghfast.top/{url}",
            url,
        ]

    for candidate_url in urls_to_try:
        req = urllib.request.Request(
            candidate_url,
            headers={"User-Agent": "Mozilla/5.0 (yidehai-video-skill/2.1)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            if tmp.stat().st_size < 10_000:
                tmp.unlink(missing_ok=True)
                continue
            tmp.replace(dest)
            return True
        except Exception:
            tmp.unlink(missing_ok=True)
            continue
    return False


def fetch_from_catalog(kind: str, count: int, catalog_path: Path, target_dir: Path) -> list[Path]:
    """0 配置模式：从 knowledge/media-catalog.json 按需下载尚未缓存的空镜/轻音乐。"""
    if not catalog_path.exists():
        return []
    try:
        cat = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    entries = list(cat.get(kind, []))
    if not entries:
        return []
    random.shuffle(entries)

    downloaded: list[Path] = []
    for item in entries:
        if len(downloaded) >= count:
            break
        url = (item.get("url") or "").strip()
        if not url or url.startswith("https://example.com"):
            continue
        ext = ".mp4" if kind == "bg_videos" else ".mp3"
        item_id = item.get("id") or hashlib.sha256(url.encode()).hexdigest()[:12]
        dest = target_dir / f"cat-{item_id}{ext}"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        if download_file(url, dest):
            downloaded.append(dest)
    return downloaded


def fetch_from_pexels(api_key: str, query: str, count: int, target_dir: Path) -> list[Path]:
    """可选免费 API 扩充：从 Pexels Videos 拉取 720p 竖屏无版权风景空镜（体积小、速度快，带 403 退避重试）。"""
    q = urllib.parse.urlencode({
        "query": query,
        "orientation": "portrait",
        "size": "medium",
        "per_page": min(max(count * 3, 8), 20),
        "page": random.randint(1, 5),
    })
    url = f"https://api.pexels.com/videos/search?{q}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": api_key, "User-Agent": "yidehai-video-skill/2.2"},
    )
    downloaded: list[Path] = []
    data = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 403 and attempt == 0:
                time.sleep(20)
                continue
            return downloaded
        except Exception:
            return downloaded
    if not data:
        return downloaded

    videos = data.get("videos", [])
    random.shuffle(videos)
    for v in videos:
        if len(downloaded) >= count:
            break
        vid = v.get("id")
        files = [
            vf for vf in v.get("video_files", [])
            if vf.get("file_type") == "video/mp4" and (vf.get("height") or 0) >= 720
        ]
        if not files:
            continue
        # 优先选 720p 附近体积适中的竖屏文件（约 3-5MB，下载快 3-5 倍，做文字底清晰度足够）
        files.sort(key=lambda x: abs((x.get("width") or 720) - 720))
        dl_url = files[0].get("link")
        if not dl_url:
            continue
        dest = target_dir / f"pexels-{vid}.mp4"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        if download_file(dl_url, dest, timeout=45):
            downloaded.append(dest)
            if len(downloaded) < count:
                time.sleep(2)
    return downloaded


def fetch_from_pixabay(api_key: str, query: str, count: int, target_dir: Path) -> list[Path]:
    """可选免费 API 扩充：从 Pixabay Videos 拉取免版权风景空镜。"""
    q = urllib.parse.urlencode({
        "key": api_key,
        "q": query,
        "video_type": "film",
        "per_page": min(max(count * 3, 8), 20),
        "page": random.randint(1, 4),
    })
    url = f"https://pixabay.com/api/videos/?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "yidehai-video-skill/1.6"})
    downloaded: list[Path] = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return downloaded

    hits = data.get("hits", [])
    random.shuffle(hits)
    for h in hits:
        if len(downloaded) >= count:
            break
        hid = h.get("id")
        vids = h.get("videos", {})
        pick = vids.get("medium") or vids.get("large") or vids.get("small")
        dl_url = pick.get("url") if isinstance(pick, dict) else None
        if not dl_url:
            continue
        dest = target_dir / f"pixabay-{hid}.mp4"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        if download_file(dl_url, dest, timeout=45):
            downloaded.append(dest)
    return downloaded


def fetch_from_jamendo(client_id: str, count: int, target_dir: Path) -> list[Path]:
    """可选免费 API 扩充：从 Jamendo 拉取 CC 协议免费纯音乐/治愈轻音乐 MP3。"""
    tags = random.choice(["piano", "ambient", "relaxing", "acoustic", "calm", "chillout"])
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "format": "json",
        "limit": min(max(count * 4, 10), 25),
        "fuzzytags": tags,
        "vocalinstrumental": "instrumental",
        "audioformat": "mp32",
        "order": "popularity_total",
        "offset": random.randint(0, 40),
    })
    url = f"https://api.jamendo.com/v3.0/tracks/?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "yidehai-video-skill/1.7"})
    downloaded: list[Path] = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return downloaded

    tracks = data.get("results", [])
    random.shuffle(tracks)
    for tr in tracks:
        if len(downloaded) >= count:
            break
        tid = tr.get("id")
        dl_url = tr.get("audiodownload") or tr.get("audio")
        if not dl_url or tr.get("audiodownload_allowed") is False:
            continue
        dest = target_dir / f"jamendo-{tid}.mp3"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        if download_file(dl_url, dest, timeout=45):
            downloaded.append(dest)
    return downloaded


def ensure_online_media(kind: str, count: int = 2, query: str | None = None, cfg: dict | None = None) -> list[Path]:
    """按需拉取在线免版权素材到本机缓存目录（先 0 配置清单，再可选免费 API）。"""
    cfg = cfg or load_config()
    target_dir = Path(cfg["cache_bg_dir"] if kind == "bg_videos" else cfg["cache_bgm_dir"])
    target_dir.mkdir(parents=True, exist_ok=True)

    got = fetch_from_catalog(kind, count, DEFAULT_CATALOG_PATH, target_dir)
    if len(got) >= count:
        return got

    remain = count - len(got)
    if kind == "bgm_tracks":
        jamendo_id = os.environ.get("JAMENDO_CLIENT_ID") or cfg.get("jamendo_client_id") or ""
        if jamendo_id and remain > 0:
            got.extend(fetch_from_jamendo(jamendo_id, remain, target_dir))
        return got

    q = query or random.choice(DEFAULT_SCENIC_QUERIES)
    pexels_key = os.environ.get("PEXELS_API_KEY") or cfg.get("pexels_api_key") or ""
    if pexels_key and remain > 0:
        got.extend(fetch_from_pexels(pexels_key, q, remain, target_dir))
        remain = count - len(got)

    pixabay_key = os.environ.get("PIXABAY_API_KEY") or cfg.get("pixabay_api_key") or ""
    if pixabay_key and remain > 0:
        got.extend(fetch_from_pixabay(pixabay_key, q, remain, target_dir))

    return got


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海本地素材路径记忆与在线空镜/BGM 按需拉取工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cfg = sub.add_parser("config", help="查看或保存本机素材目录/偏好（写入 ~/.yidehai-video/config.json）")
    p_cfg.add_argument("--show", action="store_true", help="查看当前配置（不回显密钥明文）")
    p_cfg.add_argument("--add-bg-dir", help="添加并记住本地风景空镜视频目录（供大字报使用）")
    p_cfg.add_argument("--add-footage-dir", help="添加并记住本地业务实拍素材目录（视频+图片，供实拍混剪/省点混剪使用）")
    p_cfg.add_argument("--add-bgm-dir", help="添加并记住本地免版权轻音乐目录")
    p_cfg.add_argument("--set-motion-templates-dir", help="设置本机 MotionGit 免费口播模板目录")
    p_cfg.add_argument("--bg-source", choices=["both", "local", "online"], help="背景来源策略：both(混合) / local / online")
    p_cfg.add_argument("--set-pexels-key", help="保存可选 Pexels 免费 API Key 到本机配置")
    p_cfg.add_argument("--set-pixabay-key", help="保存可选 Pixabay 免费 API Key 到本机配置")
    p_cfg.add_argument("--set-jamendo-id", help="保存可选 Jamendo 免费音乐 Client ID 到本机配置")
    p_cfg.add_argument("--mark-initialized", action="store_true", help="标记首次素材与环境初始化已完成，后续不再主动弹窗")
    p_cfg.add_argument("--dismiss-onboarding", action="store_true", help="标记用户已明确跳过首次引导，后续不再提醒")

    p_fetch = sub.add_parser("fetch", help="按需拉取在线免版权风景空镜或 BGM 到本机缓存")
    p_fetch.add_argument("--kind", choices=["bg_videos", "bgm_tracks"], default="bg_videos")
    p_fetch.add_argument("--count", type=int, default=3)
    p_fetch.add_argument("--query", help="可选英文风景检索词（仅 API 模式使用）")

    p_foot = sub.add_parser("footage", help="从本地业务实拍目录抽取未用过的视频/图片素材（全局防重）")
    p_foot.add_argument("--count", type=int, default=3, help="需要抽取的素材数量")
    p_foot.add_argument("--kind", choices=["any", "video", "image"], default="any", help="筛选类型")

    args = parser.parse_args()
    cfg = load_config()

    if args.cmd == "config":
        changed = False
        if args.add_bg_dir:
            p = str(Path(args.add_bg_dir).expanduser().resolve())
            if p not in cfg["local_bg_dirs"]:
                cfg["local_bg_dirs"].append(p)
                changed = True
            cfg["initialized"] = True
        if args.add_footage_dir:
            p = str(Path(args.add_footage_dir).expanduser().resolve())
            if p not in cfg["local_footage_dirs"]:
                cfg["local_footage_dirs"].append(p)
                changed = True
            cfg["initialized"] = True
        if args.add_bgm_dir:
            p = str(Path(args.add_bgm_dir).expanduser().resolve())
            if p not in cfg["local_bgm_dirs"]:
                cfg["local_bgm_dirs"].append(p)
                changed = True
        if args.set_motion_templates_dir:
            cfg["local_motion_templates_dir"] = str(Path(args.set_motion_templates_dir).expanduser().resolve())
            cfg["initialized"] = True
            changed = True
        if args.bg_source:
            cfg["bg_source"] = args.bg_source
            changed = True
        if args.set_pexels_key:
            cfg["pexels_api_key"] = args.set_pexels_key.strip()
            cfg["initialized"] = True
            changed = True
        if args.set_pixabay_key:
            cfg["pixabay_api_key"] = args.set_pixabay_key.strip()
            cfg["initialized"] = True
            changed = True
        if args.set_jamendo_id:
            cfg["jamendo_client_id"] = args.set_jamendo_id.strip()
            changed = True
        if args.mark_initialized:
            cfg["initialized"] = True
            changed = True
        if args.dismiss_onboarding:
            cfg["onboarding_dismissed"] = True
            cfg["initialized"] = True
            changed = True
        if changed:
            save_config(cfg)

        safe_view = {k: v for k, v in cfg.items() if "key" not in k and "client_id" not in k}
        safe_view["has_pexels_key"] = bool(cfg.get("pexels_api_key"))
        safe_view["has_pixabay_key"] = bool(cfg.get("pixabay_api_key"))
        safe_view["has_jamendo_id"] = bool(cfg.get("jamendo_client_id"))
        safe_view["config_path"] = str(CONFIG_PATH)
        print(json.dumps(safe_view, ensure_ascii=False, indent=2))

    elif args.cmd == "fetch":
        files = ensure_online_media(args.kind, count=args.count, query=args.query, cfg=cfg)
        print(json.dumps({
            "ok": True,
            "kind": args.kind,
            "downloaded": [str(f) for f in files],
        }, ensure_ascii=False, indent=2))

    elif args.cmd == "footage":
        video_exts = {".mp4", ".mov", ".m4v", ".mkv"}
        image_exts = {".jpg", ".jpeg", ".png", ".webp"}
        allow_exts = video_exts | image_exts
        if args.kind == "video":
            allow_exts = video_exts
        elif args.kind == "image":
            allow_exts = image_exts

        ledger_path = Path(cfg.get("ledger_path") or DEFAULT_LEDGER_PATH)
        used_names: set[str] = set()
        if ledger_path.exists():
            try:
                ldata = json.loads(ledger_path.read_text(encoding="utf-8"))
                for item in ldata.get("used_footage", []):
                    used_names.add(str(item))
            except Exception:
                pass

        candidates: list[Path] = []
        for d in cfg.get("local_footage_dirs", []):
            dp = Path(d).expanduser()
            if not dp.is_dir():
                continue
            for f in dp.rglob("*"):
                if f.is_file() and f.suffix.lower() in allow_exts and not f.name.startswith("."):
                    candidates.append(f)

        fresh = [f for f in candidates if f.name not in used_names]
        pool = fresh if len(fresh) >= args.count else (fresh + [f for f in candidates if f.name in used_names])
        random.shuffle(pool)
        picked = pool[: args.count]
        print(json.dumps({
            "ok": True,
            "total_scanned": len(candidates),
            "fresh_available": len(fresh),
            "picked": [
                {
                    "path": str(f),
                    "name": f.name,
                    "type": "image" if f.suffix.lower() in image_exts else "video",
                    "fresh": f.name not in used_names,
                }
                for f in picked
            ],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
