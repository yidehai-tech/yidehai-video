#!/usr/bin/env python3
"""
亿德海团队短视频批量工厂调度器（跨平台 macOS / Windows）
支持多形态混合批量出片、默认 50%「大字报」+ 50%「动效片」、合规硬拦截、全局防重、断点续跑与可视化审片页。

支持的中文/英文形态映射：
- 大字报（poster / dazibao）：调用内置 render_poster.py，8.8s 一镜到底满屏大字，9 秒出片
- 动效片（motion / openmotion / 动效视频）：自动检测本机 OpenMotion/HyperFrames 前台同步渲染；若引擎未就绪则优雅标记待渲并输出工程规范，绝不阻塞整批任务或拼凑低质占位片
"""

import argparse
import concurrent.futures
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import media_manager
import render_poster

TYPE_ALIASES = {
    "大字报": "poster",
    "大字报视频": "poster",
    "poster": "poster",
    "dazibao": "poster",
    "动效片": "motion",
    "动效视频": "motion",
    "动态卡片": "motion",
    "motion": "motion",
    "openmotion": "motion",
}

TYPE_DISPLAY = {
    "poster": "大字报",
    "motion": "动效片",
}

FORBIDDEN_TERMS = [
    "顺丰", "京东", "当场结算", "当场结钱", "秒到账", "即时到账", "立返", "马上打钱",
    "微信搜", "搜一搜", "加微信", "看主页", "点左下角", "点我头像", "点头像",
    "评论区扣", "私信我", "私信领",
]


def normalize_type(raw: str) -> str:
    key = (raw or "poster").strip().lower()
    if key in TYPE_ALIASES:
        return TYPE_ALIASES[key]
    raise ValueError(f"不支持的视频类型：{raw}（支持：大字报 / 动效片）")


def check_compliance(item: dict) -> list[str]:
    chunks = [
        str(item.get("title", "")),
        "\n".join(item["body"]) if isinstance(item.get("body"), list) else str(item.get("body", "")),
        str(item.get("question", "")),
        str(item.get("pill", "")),
        str(item.get("publish_copy", "")),
    ]
    full_text = "\n".join(chunks)
    hits = [term for term in FORBIDDEN_TERMS if term in full_text]
    return hits


def item_copy_hash(item: dict) -> str:
    title = str(item.get("title", "")).strip()
    body = item.get("body", "")
    body_str = "\n".join(body) if isinstance(body, list) else str(body)
    return hashlib.sha256((title + "\n" + body_str.strip()).encode("utf-8")).hexdigest()[:16]


def detect_openmotion_runtime() -> dict | None:
    """自动检测本机已安装且导出就绪的 OpenMotion / HyperFrames 渲染环境（不写死路径/版本）。"""
    candidates = []
    if os.environ.get("OPENMOTION_HOME"):
        candidates.append(Path(os.environ["OPENMOTION_HOME"]))
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "openmotion")
    candidates.extend([
        Path.home() / ".openmotion",
        Path.home() / "Library" / "Application Support" / "openmotion",
        Path.home() / ".local" / "share" / "openmotion",
    ])

    for om_home in candidates:
        install_json = om_home / "install.json"
        if not install_json.exists():
            continue
        try:
            meta = json.loads(install_json.read_text(encoding="utf-8"))
            app_root = Path(meta.get("appRoot", ""))
            hf_bin = app_root / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
            lock_file = app_root / "scripts" / "runtime-lock.json"
            if not hf_bin.exists() or not lock_file.exists():
                continue
            lock = json.loads(lock_file.read_text(encoding="utf-8"))
            cache_dir = om_home / "cache" / "native"
            target_key = "win-x64" if sys.platform.startswith("win") else ("mac-arm64" if os.uname().machine == "arm64" else "mac-x64")
            tinfo = lock.get("targets", {}).get(target_key, {})
            browser_info = tinfo.get("browser", {})
            media_info = tinfo.get("media", {})
            b_sha = browser_info.get("sha256", "")
            m_sha = media_info.get("sha256", "")
            b_exec = cache_dir / target_key / f"browser-{b_sha}" / browser_info.get("executable", "")
            m_dir = cache_dir / target_key / f"media-{m_sha}" / media_info.get("directory", "")
            ffmpeg_bin = m_dir / "bin" / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
            ffprobe_bin = m_dir / "bin" / ("ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
            if b_exec.exists() and ffmpeg_bin.exists() and ffprobe_bin.exists():
                return {
                    "om_home": str(om_home),
                    "app_root": str(app_root),
                    "hf_bin": str(hf_bin),
                    "browser_path": str(b_exec),
                    "ffmpeg_path": str(ffmpeg_bin),
                    "ffprobe_path": str(ffprobe_bin),
                }
        except Exception:
            continue
    return None


def build_motion_html_project(item: dict, proj_dir: Path) -> None:
    """生成符合 OpenMotion/HyperFrames lint 规范的多屏动效片 HTML 工程（0 错误 / 0 警告）。"""
    proj_dir.mkdir(parents=True, exist_ok=True)
    comp_dir = proj_dir / "compositions"
    comp_dir.mkdir(exist_ok=True)

    title = html.escape(str(item.get("title", "")).replace("\n", " "))
    raw_body = item.get("body", [])
    lines = raw_body if isinstance(raw_body, list) else [l.strip() for l in str(raw_body).splitlines() if l.strip()]
    question = html.escape(str(item.get("question", "")))
    pill = html.escape(str(item.get("pill", "亿德海 · 专人免费上门回收")))
    duration = float(item.get("duration", 10.0))

    # 拆成 3 屏核心文案
    n = max(1, len(lines))
    s1 = html.escape("\n".join(lines[: max(1, n // 3)]))
    s2 = html.escape("\n".join(lines[max(1, n // 3): max(2, 2 * n // 3)]))
    s3 = html.escape("\n".join(lines[max(2, 2 * n // 3):]) or question)

    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>{title}</title>
  <style>
    @font-face {{
      font-family: "YidehaiSans";
      src: local("PingFang SC"), local("Microsoft YaHei"), local("Hiragino Sans GB"), local("SimHei");
      font-weight: 400 900;
    }}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; background: #102A22; font-family: "YidehaiSans", sans-serif; }}
  </style>
</head>
<body>
  <div id="root" data-composition-id="root" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div data-track="main" data-start="0" data-duration="{duration:.2f}" data-composition-src="compositions/film.html"></div>
  </div>
</body>
</html>
"""
    film_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <style>
    @font-face {{
      font-family: "YidehaiSans";
      src: local("PingFang SC"), local("Microsoft YaHei"), local("Hiragino Sans GB"), local("SimHei");
      font-weight: 400 900;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; color: #FFFFFF; background: radial-gradient(circle at 50% 28%, #1C4A3B 0%, #0D221B 75%); }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 200px 72px 260px; display: flex; flex-direction: column; justify-content: space-between; align-items: center; text-align: center; }}
    .top-title {{ font-size: 76px; font-weight: 900; line-height: 1.2; color: #FFD43B; text-shadow: 0 6px 20px rgba(0,0,0,0.45); }}
    .card-box {{ position: relative; width: 100%; height: 860px; display: flex; align-items: center; justify-content: center; }}
    .slide {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 48px; border-radius: 36px; background: rgba(255,255,255,0.08); border: 2px solid rgba(255,212,59,0.28); font-size: 62px; font-weight: 800; line-height: 1.45; white-space: pre-line; opacity: 0; transform: translateY(36px) scale(0.96); }}
    .question {{ font-size: 46px; font-weight: 700; color: #FFD43B; opacity: 0; }}
    .pill {{ padding: 20px 50px; border-radius: 999px; background: rgba(0,0,0,0.58); border: 2px solid rgba(255,212,59,0.55); font-size: 38px; font-weight: 700; color: #FFFFFF; opacity: 0; transform: translateY(20px); }}
  </style>
</head>
<body>
  <div class="stage" data-composition-id="film" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div class="top-title">{title}</div>
    <div class="card-box">
      <div class="slide s1">{s1}</div>
      <div class="slide s2">{s2}</div>
      <div class="slide s3">{s3}</div>
    </div>
    <div class="question">{question}</div>
    <div class="pill">{pill}</div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".s1", {{ opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "power2.out" }}, 0.05)
      .to(".s1", {{ opacity: 0, y: -24, duration: 0.3 }}, 3.2)
      .to(".s2", {{ opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "power2.out" }}, 3.35)
      .to(".s2", {{ opacity: 0, y: -24, duration: 0.3 }}, 6.4)
      .to(".s3", {{ opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "power2.out" }}, 6.55)
      .to(".question", {{ opacity: 1, duration: 0.35 }}, 6.9)
      .to(".pill", {{ opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }}, {max(0.0, duration - 2.8):.2f});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""
    (proj_dir / "index.html").write_text(index_html, encoding="utf-8")
    (comp_dir / "film.html").write_text(film_html, encoding="utf-8")


def run_one_item(
    item: dict,
    out_root: Path,
    om_runtime: dict | None,
    silent_default: bool,
    bg_dir_override: str | None,
    bgm_dir_override: str | None,
) -> dict:
    item_id = item["id"]
    norm_type = normalize_type(item.get("type", "大字报"))
    item_dir = out_root / item_id
    item_dir.mkdir(parents=True, exist_ok=True)
    job_path = item_dir / "job.json"
    job_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

    if norm_type == "poster":
        cmd = [
            sys.executable, str(SCRIPTS_DIR / "render_poster.py"),
            "--job", str(job_path),
            "--out-dir", str(item_dir),
            "--force",
        ]
        if bg_dir_override:
            cmd += ["--bg-dir", bg_dir_override]
        if bgm_dir_override:
            cmd += ["--bgm-dir", bgm_dir_override]
        if item.get("silent", silent_default):
            cmd.append("--silent")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return {"id": item_id, "type": "poster", "status": "failed", "error": (proc.stderr or proc.stdout).strip()[-400:]}
        res = json.loads(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip().startswith("{") is False else proc.stdout)
        return {
            "id": item_id,
            "type": "poster",
            "type_zh": TYPE_DISPLAY["poster"],
            "title": item.get("title", ""),
            "status": "done",
            "mp4": res["mp4"],
            "cover_9x16": res["cover_9x16"],
            "cover_3x4": res["cover_3x4"],
            "duration": res.get("duration"),
            "bg": res.get("bg"),
            "bgm": res.get("bgm"),
        }

    # 动效片（motion）：走 OpenMotion / HyperFrames 前台同步渲染
    proj_dir = item_dir / "motion-project"
    build_motion_html_project(item, proj_dir)
    if om_runtime is None:
        return {
            "id": item_id,
            "type": "motion",
            "type_zh": TYPE_DISPLAY["motion"],
            "title": item.get("title", ""),
            "status": "pending_motion_engine",
            "project_dir": str(proj_dir),
            "note": "本机 OpenMotion 导出组件尚未就绪，已保存规范动效工程；补齐组件后重跑本命令即可自动断点续渲。",
        }

    out_mp4 = item_dir / f"{item.get('slug', item_id)}.mp4"
    env = os.environ.copy()
    env["HYPERFRAMES_FFMPEG_PATH"] = om_runtime["ffmpeg_path"]
    env["HYPERFRAMES_FFPROBE_PATH"] = om_runtime["ffprobe_path"]
    env["HYPERFRAMES_BROWSER_PATH"] = om_runtime["browser_path"]
    env["HYPERFRAMES_TELEMETRY_DISABLED"] = "1"

    cmd = ["node", om_runtime["hf_bin"], "render", "-o", str(out_mp4), str(proj_dir)]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0 or not out_mp4.exists():
        return {"id": item_id, "type": "motion", "type_zh": TYPE_DISPLAY["motion"], "title": item.get("title", ""), "status": "failed", "error": (proc.stderr or proc.stdout).strip()[-400:]}

    # 默认自动给动效片混入防重背景音乐（仅当指定 --silent 时保持无声）
    bgm_label = "silent"
    if not item.get("silent", silent_default):
        cfg = media_manager.load_config()
        ledger_path = Path(cfg["ledger_path"])
        ledger = render_poster.load_ledger(ledger_path)
        duration = float(item.get("duration", 10.0))
        bgm_dirs = [Path(bgm_dir_override)] if bgm_dir_override else (
            [Path(d) for d in cfg.get("local_bgm_dirs", [])] + [Path(cfg["cache_bgm_dir"])]
        )
        picked_bgm = render_poster.pick_unique_bgm(bgm_dirs, duration, ledger)
        if picked_bgm is None:
            media_manager.ensure_online_media("bgm_tracks", count=2, cfg=cfg)
            picked_bgm = render_poster.pick_unique_bgm([Path(cfg["cache_bgm_dir"])], duration, ledger)
        tmp_audio = item_dir / "_motion_bgm.wav"
        if picked_bgm is not None:
            bgm_src, bgm_start = picked_bgm
            bgm_label = f"{bgm_src.name}@{bgm_start:.1f}s"
        else:
            seed = int(hashlib.sha256(f"{item_id}-{datetime.now().isoformat()}".encode()).hexdigest()[:8], 16)
            render_poster.generate_gentle_ambient_wav(tmp_audio, duration, seed)
            bgm_src, bgm_start = tmp_audio, 0.0
            bgm_label = "builtin-ambient-chord"
        muxed_mp4 = item_dir / f"{item.get('slug', item_id)}.muxed.mp4"
        mux_proc = subprocess.run([
            om_runtime["ffmpeg_path"], "-y", "-v", "error",
            "-i", str(out_mp4),
            "-stream_loop", "-1", "-ss", f"{bgm_start:.2f}", "-i", str(bgm_src),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-af", f"volume=0.80,afade=t=in:st=0:d=0.25,afade=t=out:st={max(0, duration-0.7):.2f}:d=0.7",
            "-t", f"{duration:.2f}", "-movflags", "+faststart",
            str(muxed_mp4),
        ], capture_output=True, text=True)
        if mux_proc.returncode == 0 and muxed_mp4.exists():
            muxed_mp4.replace(out_mp4)
            render_poster.save_ledger(ledger_path, ledger)
        tmp_audio.unlink(missing_ok=True)

    cover_9x16 = item_dir / "cover-9x16.jpg"
    cover_3x4 = item_dir / "cover-3x4.jpg"
    subprocess.run([om_runtime["ffmpeg_path"], "-y", "-v", "error", "-ss", "1.0", "-i", str(out_mp4), "-frames:v", "1", "-q:v", "2", str(cover_9x16)], check=False)
    if cover_9x16.exists():
        subprocess.run([om_runtime["ffmpeg_path"], "-y", "-v", "error", "-i", str(cover_9x16), "-vf", "crop=1080:1440:0:180", "-q:v", "2", str(cover_3x4)], check=False)

    return {
        "id": item_id,
        "type": "motion",
        "type_zh": TYPE_DISPLAY["motion"],
        "title": item.get("title", ""),
        "status": "done",
        "mp4": str(out_mp4),
        "bgm": bgm_label,
        "cover_9x16": str(cover_9x16) if cover_9x16.exists() else "",
        "cover_3x4": str(cover_3x4) if cover_3x4.exists() else "",
    }


def write_review_html(out_root: Path, results: list[dict]) -> Path:
    cards = []
    for r in results:
        rel_mp4 = os.path.relpath(r["mp4"], out_root) if r.get("mp4") else ""
        rel_cov = os.path.relpath(r["cover_9x16"], out_root) if r.get("cover_9x16") else ""
        badge = html.escape(r.get("type_zh", r.get("type", "")))
        status = html.escape(r.get("status", ""))
        title = html.escape(str(r.get("title", "")).replace("\n", " "))
        media_html = (
            f'<video controls preload="none" poster="{html.escape(rel_cov)}" src="{html.escape(rel_mp4)}"></video>'
            if rel_mp4 else f'<div class="placeholder">{html.escape(r.get("note") or r.get("error") or status)}</div>'
        )
        cards.append(f"""
        <div class="card" data-type="{html.escape(r.get('type',''))}" data-status="{status}">
          <div class="meta"><span class="tag">{badge}</span><span class="st {status}">{status}</span><span class="cid">{html.escape(r['id'])}</span></div>
          {media_html}
          <div class="title">{title}</div>
        </div>""")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>亿德海批量审片台</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif; background: #0f1412; color: #f1f5f3; margin: 0; padding: 24px; }}
  h1 {{ margin: 0 0 12px; font-size: 22px; }}
  .bar {{ display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }}
  button {{ background: #1e2d27; color: #fff; border: 1px solid #355246; padding: 8px 14px; border-radius: 8px; cursor: pointer; }}
  button.active {{ background: #2f9e44; border-color: #2f9e44; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }}
  .card {{ background: #17201c; border: 1px solid #263830; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }}
  .meta {{ display: flex; gap: 6px; align-items: center; font-size: 12px; }}
  .tag {{ background: #264d3b; padding: 2px 8px; border-radius: 999px; }}
  .st.done {{ color: #69db7c; }} .st.pending_motion_engine {{ color: #ffd43b; }} .st.failed {{ color: #ff6b6b; }}
  .cid {{ margin-left: auto; color: #8fa399; }}
  video {{ width: 100%; aspect-ratio: 9/16; background: #000; border-radius: 8px; }}
  .placeholder {{ width: 100%; aspect-ratio: 9/16; background: #111815; border-radius: 8px; display: flex; align-items: center; justify-content: center; padding: 16px; text-align: center; font-size: 13px; color: #ffd43b; box-sizing: border-box; }}
  .title {{ font-size: 13px; line-height: 1.4; color: #dce6e0; }}
</style></head><body>
<h1>亿德海批量短视频审片台（共 {len(results)} 条）</h1>
<div class="bar">
  <button class="active" onclick="flt('all',this)">全部</button>
  <button onclick="flt('poster',this)">大字报</button>
  <button onclick="flt('motion',this)">动效片</button>
</div>
<div class="grid">{''.join(cards)}</div>
<script>
function flt(t, btn) {{
  document.querySelectorAll('.bar button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.card').forEach(c=>{{
    c.style.display = (t==='all' || c.dataset.type===t) ? 'flex' : 'none';
  }});
}}
</script></body></html>"""
    review_path = out_root / "review.html"
    review_path.write_text(page, encoding="utf-8")
    return review_path


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海批量短视频工厂（默认 50% 大字报 + 50% 动效片，支持断点续跑）")
    parser.add_argument("--manifest", required=True, help="批量任务 JSON（items 列表，每项可填 type: 大字报 / 动效片）")
    parser.add_argument("--out-dir", required=True, help="本批输出根目录")
    parser.add_argument("--workers", type=int, default=2, help="大字报并发渲染线程数（默认 2）")
    parser.add_argument("--silent", action="store_true", help="整批默认导出无声版")
    parser.add_argument("--bg-dir", help="可选覆盖背景空镜目录")
    parser.add_argument("--bgm-dir", help="可选覆盖 BGM 目录")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    items = manifest.get("items", manifest if isinstance(manifest, list) else [])
    if not items:
        raise ValueError("manifest 中没有 items 条目")

    # 1. 全批合规硬拦截 + 批内查重 + 默认 50/50 类型分配（若条目未显式指定 type）
    seen_hashes = set()
    compliance_errors = []
    for idx, it in enumerate(items):
        it.setdefault("id", f"V{idx+1:03d}")
        if not it.get("type"):
            it["type"] = "大字报" if idx % 2 == 0 else "动效片"
        it["slug"] = it.get("slug") or it["id"].lower()
        hits = check_compliance(it)
        if hits:
            compliance_errors.append(f"{it['id']} 命中红线词：{', '.join(hits)}")
        h = item_copy_hash(it)
        if h in seen_hashes:
            compliance_errors.append(f"{it['id']} 与本批前文文案完全重复")
        seen_hashes.add(h)

    if compliance_errors:
        print(json.dumps({"ok": False, "stage": "precheck", "errors": compliance_errors}, ensure_ascii=False, indent=2))
        sys.exit(2)

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    progress_path = out_root / "progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}

    # 2. 预检 OpenMotion 动效片引擎（不阻塞大字报渲染）
    need_motion = any(normalize_type(it["type"]) == "motion" for it in items)
    om_runtime = detect_openmotion_runtime() if need_motion else None

    # 3. 断点续跑：拆分待跑项（大字报支持并发，动效片顺序渲染稳妥防无头浏览器争抢）
    todo_poster = []
    todo_motion = []
    for it in items:
        prev = progress.get(it["id"])
        if prev and prev.get("status") == "done" and prev.get("mp4") and Path(prev["mp4"]).exists():
            continue
        if normalize_type(it["type"]) == "poster":
            todo_poster.append(it)
        else:
            todo_motion.append(it)

    if todo_poster:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [
                ex.submit(run_one_item, it, out_root, None, args.silent, args.bg_dir, args.bgm_dir)
                for it in todo_poster
            ]
            for fut in concurrent.futures.as_completed(futs):
                res = fut.result()
                progress[res["id"]] = res
                progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

    for it in todo_motion:
        res = run_one_item(it, out_root, om_runtime, args.silent, args.bg_dir, args.bgm_dir)
        progress[res["id"]] = res
        progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

    ordered = [progress[it["id"]] for it in items if it["id"] in progress]
    review_html = write_review_html(out_root, ordered)

    summary = {
        "ok": True,
        "total": len(ordered),
        "done": sum(1 for r in ordered if r["status"] == "done"),
        "pending_motion_engine": sum(1 for r in ordered if r["status"] == "pending_motion_engine"),
        "failed": sum(1 for r in ordered if r["status"] == "failed"),
        "review_html": str(review_html),
        "progress_json": str(progress_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
