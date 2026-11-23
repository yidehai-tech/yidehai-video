#!/usr/bin/env python3
"""
亿德海 8.8 秒一镜到底「大字报」离线一键合成脚本（跨平台 macOS / Windows）
- 1:1 复刻真实日更版式：1080×1920 30fps，风景/实拍空镜背景 + 四段式居中描边大字 + 细线圆点分隔符 + 半透明圆角胶囊条
- 内置 4 层防重去重机制（文案查重 + 背景素材时间窗防重账本 + 视觉指纹微调 + BGM 轮换/无声模式）
- 同步产出：9:16 成片 MP4 + 9:16 封面 + 3:4 小红书封面
"""

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH = 1080
HEIGHT = 1920

THEMES = {
    "warm_yellow": {
        "name": "暖阳黄",
        "accent": (245, 200, 66, 255),      # #F5C842
        "body": (255, 255, 255, 255),
        "pill_text": (245, 212, 102, 255),
        "pill_bg": (18, 20, 22, 150),
        "stroke": (18, 20, 24, 255),
    },
    "lavender": {
        "name": "薰衣草紫",
        "accent": (205, 186, 255, 255),     # #CDBA FF
        "body": (255, 255, 255, 255),
        "pill_text": (245, 245, 250, 255),
        "pill_bg": (22, 22, 30, 150),
        "stroke": (20, 18, 30, 255),
    },
    "warm_gold": {
        "name": "暖米金",
        "accent": (244, 226, 156, 255),     # #F4E29C
        "body": (255, 255, 255, 255),
        "pill_text": (244, 226, 156, 255),
        "pill_bg": (16, 24, 18, 150),
        "stroke": (15, 22, 16, 255),
    },
}


def find_chinese_bold_font() -> tuple[str, int]:
    """跨平台自动定位高质量中文粗体字体，返回 (font_path, face_index)。"""
    candidates = [
        # macOS
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),   # W6 Bold
        ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
        ("/Library/Fonts/Songti.ttc", 0),
        # Windows
        (r"C:\Windows\Fonts\msyhbd.ttc", 0),                 # 微软雅黑 Bold
        (r"C:\Windows\Fonts\simhei.ttf", 0),                 # 黑体
        (r"C:\Windows\Fonts\msyh.ttc", 0),
        # Linux
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ]
    for path, idx in candidates:
        if os.path.exists(path):
            return path, idx
    raise FileNotFoundError("未找到可用的中文字体，请安装思源黑体或微软雅黑。")


def load_font(font_path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_path, size=size, index=index)
    except Exception:
        return ImageFont.truetype(font_path, size=size, index=0)


def ffprobe_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out)


def load_ledger(ledger_path: Path) -> dict:
    if ledger_path.exists():
        return json.loads(ledger_path.read_text(encoding="utf-8"))
    return {"used_copies": [], "used_bg_segments": [], "used_bgm": [], "history": []}


def save_ledger(ledger_path: Path, data: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_unique_bg_segment(bg_dir: Path, duration: float, ledger: dict) -> tuple[Path, float]:
    """从背景素材池自动挑选未用过的 (文件, 起始秒) 时间窗，确保画面绝不重复。"""
    videos = sorted(
        p for p in bg_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    )
    if not videos:
        raise FileNotFoundError(f"背景素材目录为空：{bg_dir}")

    used_keys = set(ledger.get("used_bg_segments", []))
    window_step = math.ceil(duration + 0.5)
    random.shuffle(videos)

    for v in videos:
        try:
            vdur = ffprobe_duration(str(v))
        except Exception:
            continue
        seg_candidates = []
        if vdur < duration:
            key = f"{v.name}@0"
            if key not in used_keys:
                seg_candidates.append((v, 0.0, key))
        else:
            start = 0
            while start + duration <= vdur + 0.05:
                key = f"{v.name}@{start}"
                if key not in used_keys:
                    seg_candidates.append((v, float(start), key))
                start += window_step
        if seg_candidates:
            chosen_path, chosen_start, chosen_key = random.choice(seg_candidates)
            ledger.setdefault("used_bg_segments", []).append(chosen_key)
            return chosen_path, chosen_start

    raise RuntimeError(
        f"背景素材池 {bg_dir} 中的可用不重复片段已全部用完（共已用 {len(used_keys)} 段），请补充新空镜素材！"
    )


def wrap_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按像素宽度智能断行，避免单字孤行。"""
    text = text.strip()
    if not text:
        return []
    bbox = draw.textbbox((0, 0), text, font=font)
    if (bbox[2] - bbox[0]) <= max_width:
        return [text]

    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        tb = draw.textbbox((0, 0), test, font=font)
        if (tb[2] - tb[0]) <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)

    # 避免最后一行只剩 1-2 个孤字
    if len(lines) >= 2 and len(lines[-1]) <= 2 and len(lines[-2]) >= 5:
        move = lines[-2][-2:]
        lines[-2] = lines[-2][:-2]
        lines[-1] = move + lines[-1]
    return lines


def draw_outlined_centered_text(
    img: Image.Image,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    stroke_fill: tuple[int, int, int, int],
    stroke_width: int,
) -> int:
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (WIDTH - tw) // 2 - bbox[0]

    # 柔和阴影增强高对比度
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.text(
        (x, y + 5), text, font=font,
        fill=(0, 0, 0, 155), stroke_width=stroke_width + 2, stroke_fill=(0, 0, 0, 155),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=4))
    img.alpha_composite(shadow)

    draw = ImageDraw.Draw(img)
    draw.text(
        (x, y), text, font=font,
        fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
    )
    return th


def build_overlay_png(
    title: str,
    body_lines: list[str],
    question: str,
    pill: str,
    theme_key: str,
    out_png: Path,
) -> None:
    theme = THEMES[theme_key]
    font_path, font_idx = find_chinese_bold_font()

    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    # 轻微全局压暗 + 上下轻渐变暗角，保证任何亮色风景空镜下文字都清晰锐利
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    for row in range(HEIGHT):
        # 顶部和中部柔和压暗，底部稍深护住胶囊条
        t = row / HEIGHT
        alpha = int(52 + 34 * math.sin(math.pi * t) + (36 if t > 0.78 else 0))
        vdraw.line([(0, row), (WIDTH, row)], fill=(8, 12, 16, min(alpha, 130)))
    img.alpha_composite(vignette)

    draw = ImageDraw.Draw(img)

    title_segs = [s.strip() for s in title.split("\n") if s.strip()]
    max_title_len = max((len(s) for s in title_segs), default=8)
    title_size = 82 if max_title_len <= 10 else (72 if max_title_len <= 12 else 64)
    title_font = load_font(font_path, font_idx, title_size)
    body_font = load_font(font_path, font_idx, 52)
    q_font = load_font(font_path, font_idx, 42)
    pill_font = load_font(font_path, font_idx, 34)

    max_title_w = WIDTH - 110
    max_body_w = WIDTH - 148
    max_q_w = WIDTH - 150

    wrapped_title = []
    for seg in title_segs:
        wrapped_title.extend(wrap_line(draw, seg, title_font, max_title_w))

    wrapped_body = []
    for seg in body_lines:
        wrapped_body.extend(wrap_line(draw, seg, body_font, max_body_w))

    wrapped_q = []
    for seg in question.split("\n"):
        wrapped_q.extend(wrap_line(draw, seg, q_font, max_q_w))

    # 动态缩字防溢出安全区（正文较多时平滑缩小字号）
    if len(wrapped_body) > 12:
        body_font = load_font(font_path, font_idx, 46)
        wrapped_body = []
        for seg in body_lines:
            wrapped_body.extend(wrap_line(draw, seg, body_font, max_body_w))

    # 计算垂直布局
    title_step = 104
    body_step = 74 if len(wrapped_body) <= 12 else 66
    q_step = 58

    title_block_h = len(wrapped_title) * title_step
    divider_h = 46
    body_block_h = len(wrapped_body) * body_step
    q_block_h = len(wrapped_q) * q_step if wrapped_q else 0

    content_h = title_block_h + divider_h + body_block_h + (28 + q_block_h if q_block_h else 0)
    # 主内容区位于 y=165..1540 之间居中（给底部胶囊条和平台 UI 留足安全区）
    safe_top = 175
    safe_bottom = 1545
    y = safe_top + max(0, (safe_bottom - safe_top - content_h) // 2)

    # ① 顶部大标题
    for line in wrapped_title:
        draw_outlined_centered_text(img, y, line, title_font, theme["accent"], theme["stroke"], stroke_width=6)
        y += title_step

    # 细横线 + 中间圆点分隔符（1:1 复刻实发版式）
    div_y = y + 14
    line_half = 175
    cx = WIDTH // 2
    d = ImageDraw.Draw(img)
    d.line([(cx - line_half, div_y), (cx - 18, div_y)], fill=theme["accent"], width=3)
    d.line([(cx + 18, div_y), (cx + line_half, div_y)], fill=theme["accent"], width=3)
    d.ellipse([(cx - 5, div_y - 5), (cx + 5, div_y + 5)], fill=theme["accent"])
    y += divider_h

    # ② 中部正文
    for line in wrapped_body:
        draw_outlined_centered_text(img, y, line, body_font, theme["body"], theme["stroke"], stroke_width=5)
        y += body_step

    # ③ 底部轻互动问句
    if wrapped_q:
        y += 24
        for line in wrapped_q:
            draw_outlined_centered_text(img, y, line, q_font, theme["accent"], theme["stroke"], stroke_width=4)
            y += q_step

    # ④ 底部半透明圆角胶囊条（固定位于 y=1600 附近，避开抖音底部文案栏）
    if pill.strip():
        pb = d.textbbox((0, 0), pill, font=pill_font)
        pw = pb[2] - pb[0]
        ph = pb[3] - pb[1]
        pad_x, pad_y = 44, 18
        box_w = pw + pad_x * 2
        box_h = ph + pad_y * 2
        pill_y = max(y + 42, 1605)
        pill_y = min(pill_y, 1665)
        x0 = (WIDTH - box_w) // 2
        y0 = pill_y
        d.rounded_rectangle(
            [(x0, y0), (x0 + box_w, y0 + box_h)],
            radius=box_h // 2,
            fill=theme["pill_bg"],
        )
        tx = x0 + pad_x - pb[0]
        ty = y0 + pad_y - pb[1]
        d.text((tx, ty), pill, font=pill_font, fill=theme["pill_text"])

    img.save(out_png, "PNG")


def render_poster_video(
    bg_video: Path | None,
    bg_start: float,
    overlay_png: Path,
    out_mp4: Path,
    duration: float,
    bgm_audio: Path | None,
    anti_dup_seed: int,
) -> None:
    rng = random.Random(anti_dup_seed)
    zoom = rng.uniform(1.02, 1.06)
    bright = rng.uniform(-0.02, 0.02)
    contrast = rng.uniform(0.98, 1.04)
    sat = rng.uniform(0.98, 1.06)
    do_hflip = rng.choice([True, False])

    scaled_w = int(WIDTH * zoom) // 2 * 2
    scaled_h = int(HEIGHT * zoom) // 2 * 2

    cmd = ["ffmpeg", "-y", "-v", "error"]
    if bg_video is not None:
        vdur = ffprobe_duration(str(bg_video))
        if vdur < duration + bg_start:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-ss", f"{bg_start:.2f}", "-i", str(bg_video)]
        vf_parts = [
            f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase",
            f"crop={WIDTH}:{HEIGHT}",
        ]
        if do_hflip:
            vf_parts.append("hflip")
        vf_parts.append(f"eq=brightness={bright:.3f}:contrast={contrast:.3f}:saturation={sat:.3f}")
        vf_parts.append("fps=30,format=rgba")
        bg_chain = ",".join(vf_parts)
    else:
        # 兜底：无外部背景视频时生成缓慢流动的治愈森林绿渐变背景
        cmd += [
            "-f", "lavfi",
            "-i", f"color=c=#142B24:s={WIDTH}x{HEIGHT}:r=30:d={duration:.2f}",
        ]
        bg_chain = "format=rgba"

    cmd += ["-loop", "1", "-t", f"{duration:.2f}", "-i", str(overlay_png)]

    if bgm_audio is not None:
        cmd += ["-stream_loop", "-1", "-i", str(bgm_audio)]

    filter_complex = (
        f"[0:v]{bg_chain}[bg];"
        f"[1:v]format=rgba,fade=t=in:st=0:d=0.18:alpha=1[ov];"
        f"[bg][ov]overlay=0:0:shortest=1,format=yuv420p[vout]"
    )
    cmd += ["-filter_complex", filter_complex, "-map", "[vout]"]

    if bgm_audio is not None:
        cmd += ["-map", "2:a:0", "-c:a", "aac", "-b:a", "128k", "-af", f"volume=0.35,afade=t=out:st={max(0, duration-0.8):.2f}:d=0.8"]
    else:
        cmd += ["-an"]

    cmd += [
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        "-metadata", f"creation_time={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        str(out_mp4),
    ]
    subprocess.check_call(cmd)


def export_covers(mp4_path: Path, out_dir: Path) -> tuple[Path, Path]:
    cover_9x16 = out_dir / "cover-9x16.jpg"
    cover_3x4 = out_dir / "cover-3x4.jpg"
    subprocess.check_call([
        "ffmpeg", "-y", "-v", "error",
        "-ss", "1.5", "-i", str(mp4_path),
        "-frames:v", "1", "-q:v", "2",
        str(cover_9x16),
    ])
    # 3:4 小红书封面（1080×1440）：居中裁切核心文字区，避免标题/胶囊条被切
    subprocess.check_call([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(cover_9x16),
        "-vf", "crop=1080:1440:0:170",
        "-q:v", "2",
        str(cover_3x4),
    ])
    return cover_9x16, cover_3x4


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海 8.8 秒一镜到底大字报离线合成工具（带防重账本）")
    parser.add_argument("--job", required=True, help="大字报配置 JSON 路径")
    parser.add_argument("--bg", help="指定单个背景空镜视频路径")
    parser.add_argument("--bg-dir", help="背景空镜素材池目录（自动抽取未用过的时间窗）")
    parser.add_argument("--bgm", help="可选背景音乐文件；不传则出无声版（推荐发布时挂平台热门轻音乐）")
    parser.add_argument("--ledger", default="used_history.json", help="防重账本 JSON 路径")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument("--force", action="store_true", help="强制覆盖同文案查重限制")
    args = parser.parse_args()

    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    title = job["title"].strip()
    body = job["body"]
    body_lines = body if isinstance(body, list) else [l.strip() for l in body.splitlines() if l.strip()]
    question = job.get("question", "").strip()
    pill = job.get("pill", "亿德海 · 5公斤起专人免费上门").strip()
    theme_key = job.get("theme", random.choice(list(THEMES.keys())))
    if theme_key not in THEMES:
        raise ValueError(f"未知主题 {theme_key}，可选：{list(THEMES.keys())}")

    # 1. 文案防重校验
    ledger_path = Path(args.ledger)
    ledger = load_ledger(ledger_path)
    copy_hash = hashlib.sha256((title + "\n" + "\n".join(body_lines)).encode("utf-8")).hexdigest()[:16]
    if copy_hash in ledger.get("used_copies", []) and not args.force:
        raise RuntimeError(f"检测到重复文案（hash={copy_hash}），已阻止重复生成！如需强制重渲请加 --force。")

    # 2. 时长微抖动（8.6~9.0s，既贴合 8.8s 标杆又避免批量文件时长完全雷同）
    duration = float(job.get("duration", round(random.uniform(8.6, 9.0), 2)))

    # 3. 背景视频与时间窗防重
    bg_video: Path | None = None
    bg_start = 0.0
    if args.bg:
        bg_video = Path(args.bg)
    elif args.bg_dir:
        bg_video, bg_start = pick_unique_bg_segment(Path(args.bg_dir), duration, ledger)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = job.get("slug", f"poster-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    out_mp4 = out_dir / f"{slug}.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        overlay_png = Path(tmp) / "overlay.png"
        build_overlay_png(title, body_lines, question, pill, theme_key, overlay_png)
        seed = int(hashlib.sha256(f"{copy_hash}-{datetime.now().isoformat()}".encode()).hexdigest()[:8], 16)
        render_poster_video(
            bg_video=bg_video,
            bg_start=bg_start,
            overlay_png=overlay_png,
            out_mp4=out_mp4,
            duration=duration,
            bgm_audio=Path(args.bgm) if args.bgm else None,
            anti_dup_seed=seed,
        )

    cover_9x16, cover_3x4 = export_covers(out_mp4, out_dir)

    if copy_hash not in ledger.get("used_copies", []):
        ledger.setdefault("used_copies", []).append(copy_hash)
    ledger.setdefault("history", []).append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "slug": slug,
        "title": title,
        "copy_hash": copy_hash,
        "theme": theme_key,
        "duration": duration,
        "bg": f"{bg_video.name}@{bg_start:.1f}s" if bg_video else "solid-fallback",
        "output": str(out_mp4),
    })
    save_ledger(ledger_path, ledger)

    print(json.dumps({
        "ok": True,
        "mp4": str(out_mp4),
        "cover_9x16": str(cover_9x16),
        "cover_3x4": str(cover_3x4),
        "theme": theme_key,
        "duration": duration,
        "bg": f"{bg_video.name}@{bg_start:.1f}s" if bg_video else "solid-fallback",
        "copy_hash": copy_hash,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
