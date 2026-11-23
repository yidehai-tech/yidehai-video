#!/usr/bin/env python3
"""
亿德海团队短视频本地配置与在线免版权素材按需管理器（纯标准库，跨平台 macOS / Windows）
- 持久化保存同事本机素材目录与防重账本路径到 ~/.yidehai-video/config.json（绝不提交进 Git）
- 支持双模式在线按需拉取空镜/轻音乐到 ~/.yidehai-video/cache/：
  1) 0 配置直链清单模式（读取 knowledge/media-catalog.json 中的精选免版权或团队共享直链，按需下载）
  2) 可选免费 API 无限扩充模式（配置 Pexels / Pixabay 免费 API Key 后自动按竖屏风景关键词补库）
"""

import argparse
import hashlib
import json
import os
import random
import stat
import sys
import urllib.parse
import urllib.request
from pathlib import Path

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
    data.setdefault("ledger_path", str(DEFAULT_LEDGER_PATH))
    data.setdefault("cache_bg_dir", str(CACHE_BG_DIR))
    data.setdefault("cache_bgm_dir", str(CACHE_BGM_DIR))
    data.setdefault("bg_source", "both")  # both | local | online
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
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (yidehai-video-skill/1.6)"},
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
            return False
        tmp.replace(dest)
        return True
    except Exception:
        tmp.unlink(missing_ok=True)
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
    """可选免费 API 扩充：从 Pexels Videos 拉取高清竖屏无版权风景空镜。"""
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
        headers={"Authorization": api_key, "User-Agent": "yidehai-video-skill/1.6"},
    )
    downloaded: list[Path] = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return downloaded

    videos = data.get("videos", [])
    random.shuffle(videos)
    for v in videos:
        if len(downloaded) >= count:
            break
        vid = v.get("id")
        files = [
            vf for vf in v.get("video_files", [])
            if vf.get("file_type") == "video/mp4" and (vf.get("height") or 0) >= 960
        ]
        if not files:
            continue
        # 优先选 1080p 附近体积适中的高清文件
        files.sort(key=lambda x: abs((x.get("width") or 1080) - 1080))
        dl_url = files[0].get("link")
        if not dl_url:
            continue
        dest = target_dir / f"pexels-{vid}.mp4"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        if download_file(dl_url, dest, timeout=45):
            downloaded.append(dest)
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
    p_cfg.add_argument("--add-bg-dir", help="添加并记住本地背景视频目录")
    p_cfg.add_argument("--add-bgm-dir", help="添加并记住本地轻音乐目录")
    p_cfg.add_argument("--bg-source", choices=["both", "local", "online"], help="背景来源策略：both(混合) / local / online")
    p_cfg.add_argument("--set-pexels-key", help="保存可选 Pexels 免费 API Key 到本机配置")
    p_cfg.add_argument("--set-pixabay-key", help="保存可选 Pixabay 免费 API Key 到本机配置")
    p_cfg.add_argument("--set-jamendo-id", help="保存可选 Jamendo 免费音乐 Client ID 到本机配置")

    p_fetch = sub.add_parser("fetch", help="按需拉取在线免版权风景空镜或 BGM 到本机缓存")
    p_fetch.add_argument("--kind", choices=["bg_videos", "bgm_tracks"], default="bg_videos")
    p_fetch.add_argument("--count", type=int, default=3)
    p_fetch.add_argument("--query", help="可选英文风景检索词（仅 API 模式使用）")

    args = parser.parse_args()
    cfg = load_config()

    if args.cmd == "config":
        changed = False
        if args.add_bg_dir:
            p = str(Path(args.add_bg_dir).expanduser().resolve())
            if p not in cfg["local_bg_dirs"]:
                cfg["local_bg_dirs"].append(p)
                changed = True
        if args.add_bgm_dir:
            p = str(Path(args.add_bgm_dir).expanduser().resolve())
            if p not in cfg["local_bgm_dirs"]:
                cfg["local_bgm_dirs"].append(p)
                changed = True
        if args.bg_source:
            cfg["bg_source"] = args.bg_source
            changed = True
        if args.set_pexels_key:
            cfg["pexels_api_key"] = args.set_pexels_key.strip()
            changed = True
        if args.set_pixabay_key:
            cfg["pixabay_api_key"] = args.set_pixabay_key.strip()
            changed = True
        if args.set_jamendo_id:
            cfg["jamendo_client_id"] = args.set_jamendo_id.strip()
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


if __name__ == "__main__":
    main()
