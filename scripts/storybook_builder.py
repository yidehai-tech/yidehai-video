#!/usr/bin/env python3
"""
亿德海「图文故事片」一鱼两吃构建器（v2.11.0 · 跨平台 macOS / Windows）

输入：4–6 张风格统一的分镜图（来源由成员 5 选 1 确认：当前 Agent 内置生图 / 即梦 CLI / 云端聚合 API 生图 / 免费图库 API / 本地图片）
输出：
  1. 短视频成片（调用 package_ai_video.py：图片自动 Ken Burns 平滑推镜 + Edge-TTS 旁白 + EBU R128 响度归一化无版权 BGM +
     HeyGen HyperFrames 高画质字幕/顶标渲染 + 无品牌浮条利落收尾 + 8 帧质检图 + 双封面）
  2. 小红书 / 抖音图文轮播套图（xhs-carousel/ 下自动生成 1080x1440 3:4 带高清描边文案的轮播图组）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import api_image_runner  # noqa: E402
from media_manager import CACHE_IMG_DIR, check_forbidden_terms, load_config, safe_child_path, sanitize_slug  # noqa: E402
from package_ai_video import find_cjk_font  # noqa: E402

DEFAULT_NO_TEXT_SUFFIX = "画面中绝对不要出现任何文字、汉字、英文字母、数字、气泡框、水印和 logo。"


def render_xhs_carousel(panels: list[dict[str, Any]], out_dir: Path, font_path: Path, title: str) -> list[str]:
    """将 4–6 张分镜图自动排成 1080x1440（3:4）小红书/抖音高清图文轮播套图。"""
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    carousel_dir = out_dir / "xhs-carousel"
    carousel_dir.mkdir(parents=True, exist_ok=True)
    width, height = 1080, 1440
    saved: list[str] = []

    def fit_font(text: str, start_size: int, max_width: int, min_size: int = 34):
        size = start_size
        while size >= min_size:
            f = ImageFont.truetype(str(font_path), size)
            bbox = f.getbbox(text)
            if (bbox[2] - bbox[0]) <= max_width:
                return f
            size -= 2
        return ImageFont.truetype(str(font_path), min_size)

    def wrap_lines(text: str, max_chars: int = 14) -> list[str]:
        s = text.strip()
        if not s:
            return []
        lines: list[str] = []
        for para in s.splitlines():
            p = para.strip()
            while len(p) > max_chars:
                lines.append(p[:max_chars])
                p = p[max_chars:]
            if p:
                lines.append(p)
        return lines

    for idx, panel in enumerate(panels):
        img_path = Path(panel["image"]).expanduser().resolve()
        if not img_path.is_file():
            raise FileNotFoundError(f"分镜图不存在：{img_path}")
        base = Image.open(img_path).convert("RGBA")
        src_w, src_h = base.size
        target_ratio = width / height
        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            new_h = height
            new_w = int(round(src_w * (height / src_h)))
        else:
            new_w = width
            new_h = int(round(src_h * (width / src_w)))
        resized = base.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - width) // 2
        top = max(0, (new_h - height) // 3)
        canvas = resized.crop((left, top, left + width, top + height))

        # 上下柔和暗角，确保大字可读
        grad = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grad)
        for y in range(int(height * 0.28)):
            alpha = int(165 * (1 - y / (height * 0.28)) ** 1.4)
            gdraw.line([(0, y), (width, y)], fill=(12, 18, 16, alpha))
        for i in range(int(height * 0.30)):
            y = height - 1 - i
            alpha = int(190 * (1 - i / (height * 0.30)) ** 1.35)
            gdraw.line([(0, y), (width, y)], fill=(12, 18, 16, alpha))
        canvas = Image.alpha_composite(canvas, grad)
        draw = ImageDraw.Draw(canvas)

        # 第 1 张作为首图叠加主标题，其余叠加页码 + 分镜文案
        if idx == 0 and title:
            t_lines = wrap_lines(title, max_chars=10)[:2]
            y_cur = 120
            for li, line in enumerate(t_lines):
                f = fit_font(line, 96, int(width * 0.88))
                bb = f.getbbox(line)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                color = (255, 255, 255, 255) if li == 0 else (255, 227, 50, 255)
                draw.text(((width - tw) // 2, y_cur), line, font=f, fill=color, stroke_width=8, stroke_fill=(16, 16, 16, 255))
                y_cur += th + 24

        badge = f"{idx + 1} / {len(panels)}"
        bf = fit_font(badge, 32, 200, min_size=24)
        bb = bf.getbbox(badge)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        draw.rounded_rectangle([width - bw - 84, 48, width - 44, 48 + bh + 22], radius=24, fill=(0, 0, 0, 145))
        draw.text((width - bw - 64, 56), badge, font=bf, fill=(255, 255, 255, 240))

        caption = str(panel.get("caption") or panel.get("narration") or "").strip()
        if caption:
            c_lines = wrap_lines(caption, max_chars=15)[:3]
            y_cur = height - 90 - len(c_lines) * 66
            for line in c_lines:
                f = fit_font(line, 52, int(width * 0.88), min_size=34)
                bb = f.getbbox(line)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                draw.text(((width - tw) // 2, y_cur), line, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(16, 16, 16, 255))
                y_cur += th + 18

        out_jpg = carousel_dir / f"{idx + 1:02d}-{'封面' if idx == 0 else '分镜'}.jpg"
        canvas.convert("RGB").save(out_jpg, "JPEG", quality=92)
        saved.append(str(out_jpg))
    return saved


def ensure_panel_images(
    job: dict[str, Any],
    panels: list[dict[str, Any]],
    slug: str,
    generate_images: bool = False,
    image_model: str = "",
    image_ratio: str = "9:16",
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """若开启自动生图或 job 设为 api_image，为缺少本地图片的分镜自动调用云端聚合 API 生图。"""
    want_gen = bool(generate_images or str(job.get("image_source") or "").strip() == "api_image")
    if not want_gen:
        return []
    cfg = load_config()
    base_cache = cache_dir or Path(cfg.get("cache_img_dir") or CACHE_IMG_DIR)
    panel_dir = base_cache / "panels" / slug
    style_prefix = str(job.get("style_prefix") or "").strip()
    character_lock = str(job.get("character_lock") or "").strip()
    no_text_suffix = str(job.get("no_text_suffix") or DEFAULT_NO_TEXT_SUFFIX).strip()
    model = (image_model or str(job.get("image_model") or "")).strip()
    ratio = str(job.get("image_ratio") or image_ratio or "9:16").strip()

    generated: list[dict[str, Any]] = []
    for idx, panel in enumerate(panels, 1):
        raw_img = str(panel.get("image") or "").strip()
        target = Path(raw_img).expanduser().resolve() if raw_img else (panel_dir / f"{idx:02d}.png")
        if target.is_file() and target.stat().st_size > 2048:
            panel["image"] = str(target)
            generated.append({"panel": idx, "skipped": True, "file": str(target)})
            continue
        p_prompt = str(panel.get("prompt") or "").strip()
        if not p_prompt:
            raise FileNotFoundError(f"第 {idx} 幕既无已有图片（{target}），也未提供 prompt 无法自动生图。")
        full_prompt = " ".join(x for x in (style_prefix, character_lock, p_prompt, no_text_suffix) if x)
        res = api_image_runner.generate_one(
            prompt=full_prompt,
            out_path=target,
            model=model,
            ratio=ratio,
        )
        panel["image"] = res["file"]
        generated.append({"panel": idx, **res})
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海「图文故事片」一鱼两吃构建器（短视频 + 小红书 3:4 轮播图）")
    parser.add_argument("--job", required=True, help="图文故事片配置 JSON 路径")
    parser.add_argument("--out-dir", default="outputs", help="输出根目录")
    parser.add_argument("--organize-by-date", action="store_true", help="按 YYYY-MM-DD/ 归档")
    parser.add_argument("--quality", choices=["draft", "looks", "delivery"], default="delivery")
    parser.add_argument("--silent", action="store_true", help="视频不叠加 BGM（保留干声旁白）")
    parser.add_argument("--carousel-only", action="store_true", help="仅导出小红书 3:4 轮播套图，不渲染视频")
    parser.add_argument("--generate-images", action="store_true", help="自动复用云端 API Key 为带 prompt 的分镜生图（已存在自动跳过）")
    parser.add_argument("--image-model", default="", help="可选覆盖生图模型（如 gemini-3.1-flash-lite-image / doubao-seedream-5-5）")
    parser.add_argument("--image-ratio", default="9:16", help="生图比例（默认 9:16）")
    args = parser.parse_args()

    job = json.loads(Path(args.job).expanduser().read_text(encoding="utf-8"))
    panels = job.get("panels") or []
    if not panels:
        raise ValueError("storybook job 必须提供非空的 panels 分镜列表。")

    # 合规硬红线预检
    texts = [
        str(job.get("title", "")),
        str(job.get("copy", "")),
        " ".join(job.get("hashtags", [])),
    ]
    for p in panels:
        texts.append(str(p.get("caption", "")))
        texts.append(str(p.get("narration", "")))
        texts.append(str(p.get("prompt", "")))
    hits = check_forbidden_terms(texts)
    if hits:
        raise ValueError(f"合规硬红线拦截！图文故事片命中禁用词：{', '.join(hits)}")

    slug = sanitize_slug(job.get("slug", "storybook"), fallback="storybook")
    font_path = find_cjk_font()

    out_root = Path(args.out_dir).expanduser().resolve()
    gen_logs = ensure_panel_images(
        job=job,
        panels=panels,
        slug=slug,
        generate_images=args.generate_images,
        image_model=args.image_model,
        image_ratio=args.image_ratio,
        cache_dir=(safe_child_path(out_root, slug) if args.carousel_only else None),
    )

    if args.carousel_only:
        out_dir = safe_child_path(out_root, slug)
        out_dir.mkdir(parents=True, exist_ok=True)
        carousel = render_xhs_carousel(panels, out_dir, font_path, str(job.get("title", "")))
        print(json.dumps({"ok": True, "mode": "carousel_only", "generated_images": gen_logs, "xhs_carousel": carousel}, ensure_ascii=False, indent=2))
        return

    # 拼装标准 montage job 交给 package_ai_video.py（HeyGen HyperFrames + 图片 Ken Burns 推镜 + 旁白 + EBU R128 响度归一化 BGM）
    full_narration = str((job.get("voiceover") or {}).get("text") or "").strip()
    if not full_narration:
        full_narration = "。".join(str(p.get("narration") or p.get("caption") or "").strip() for p in panels if (p.get("narration") or p.get("caption")))

    pkg_job: dict[str, Any] = {
        "slug": slug,
        "track": "storybook",
        "format_label": "图文故事片",
        "mode": "montage",
        "title": job.get("title", slug),
        "copy": job.get("copy", full_narration),
        "hashtags": job.get("hashtags", ["#旧衣回收", "#断舍离", "#亿德海"]),
        "is_ai": bool(job.get("is_ai", True)),
        "voiceover": {
            "text": full_narration,
            "voice": (job.get("voiceover") or {}).get("voice", "zh-CN-XiaoxiaoNeural"),
            "rate": (job.get("voiceover") or {}).get("rate", "+12%"),
        },
        "clips": [{"path": p["image"], **({"duration": p["duration"]} if "duration" in p else {})} for p in panels],
        "top_titles": job.get("top_titles") or [
            {"start": 0.0, "duration": 999.0, "line1": str(job.get("cover", {}).get("line1") or job.get("title", "")[:10]), "line2": str(job.get("cover", {}).get("line2") or "")}
        ],
        "cover": job.get("cover") or {"line1": str(job.get("title", ""))[:10], "line2": "专人免费上门回收"},
    }
    if job.get("captions"):
        pkg_job["captions"] = job["captions"]

    with tempfile.TemporaryDirectory() as tmp:
        pkg_job_path = Path(tmp) / "pkg_job.json"
        pkg_job_path.write_text(json.dumps(pkg_job, ensure_ascii=False, indent=2), encoding="utf-8")
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "package_ai_video.py"),
            "--job", str(pkg_job_path),
            "--out-dir", args.out_dir,
            "--quality", args.quality,
        ]
        if args.organize_by_date:
            cmd.append("--organize-by-date")
        if args.silent:
            cmd.append("--silent")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"package_ai_video 执行失败：\n{proc.stdout}\n{proc.stderr}")
        pkg_res = json.loads(proc.stdout.strip())

    video_dir = Path(pkg_res["video"]).parent
    carousel = render_xhs_carousel(panels, video_dir, font_path, str(job.get("title", "")))
    pkg_res["xhs_carousel"] = carousel
    print(json.dumps(pkg_res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
