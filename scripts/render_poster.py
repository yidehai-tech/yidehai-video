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
import struct
import subprocess
import sys
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import media_manager

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


def pick_unique_bg_segment(bg_dirs: list[Path], duration: float, ledger: dict) -> tuple[Path, float] | None:
    """从多个背景素材目录自动挑选未用过的 (文件, 起始秒) 时间窗，确保画面绝不重复。"""
    videos: list[Path] = []
    for d in bg_dirs:
        if d.exists():
            videos.extend(
                p for p in d.rglob("*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
            )
    if not videos:
        return None

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

    return None


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
    max_title_w = WIDTH - 64   # 左右各留 32px 紧凑边距，铺满屏幕
    title_size = 114
    title_font = load_font(font_path, font_idx, title_size)
    while title_size > 72:
        title_font = load_font(font_path, font_idx, title_size)
        if all((draw.textbbox((0, 0), s, font=title_font)[2] - draw.textbbox((0, 0), s, font=title_font)[0]) <= max_title_w for s in title_segs):
            break
        title_size -= 2

    max_body_w = WIDTH - 72    # 左右各留 36px 边距，让大字铺满屏幕
    max_q_w = WIDTH - 72

    # 自动最大化正文字号：在安全区高度内尽可能把字放最大（64px ~ 76px）
    safe_top = 95
    safe_bottom = 1605
    title_step = int(title_size * 1.16)
    wrapped_title = []
    for seg in title_segs:
        wrapped_title.extend(wrap_line(draw, seg, title_font, max_title_w))
    title_block_h = len(wrapped_title) * title_step
    divider_h = 40

    # 将过短的零碎换行自动合并重排，避免中间空荡荡（保留显式大段感）
    raw_body_text = "".join(body_lines) if all(len(l) <= 14 for l in body_lines) else "\n".join(body_lines)

    body_size = 76
    q_size = 54
    pill_size = 44
    while body_size >= 56:
        body_font = load_font(font_path, font_idx, body_size)
        q_font = load_font(font_path, font_idx, q_size)
        wrapped_body = []
        for seg in raw_body_text.split("\n"):
            wrapped_body.extend(wrap_line(draw, seg, body_font, max_body_w))
        wrapped_q = []
        for seg in question.split("\n"):
            wrapped_q.extend(wrap_line(draw, seg, q_font, max_q_w))
        body_step = int(body_size * 1.24)
        q_step = int(q_size * 1.26)
        total_h = title_block_h + divider_h + len(wrapped_body) * body_step + (24 + len(wrapped_q) * q_step if wrapped_q else 0)
        if total_h <= (safe_bottom - safe_top):
            break
        body_size -= 2
        q_size = max(46, int(body_size * 0.74))

    pill_font = load_font(font_path, font_idx, pill_size)
    body_block_h = len(wrapped_body) * body_step
    q_block_h = len(wrapped_q) * q_step if wrapped_q else 0
    content_h = title_block_h + divider_h + body_block_h + (24 + q_block_h if q_block_h else 0)
    y = safe_top + max(0, (safe_bottom - safe_top - content_h) // 2)

    # ① 顶部大标题
    for line in wrapped_title:
        draw_outlined_centered_text(img, y, line, title_font, theme["accent"], theme["stroke"], stroke_width=8)
        y += title_step

    # 细横线 + 中间圆点分隔符（1:1 复刻实发版式）
    div_y = y + 10
    line_half = 230
    cx = WIDTH // 2
    d = ImageDraw.Draw(img)
    d.line([(cx - line_half, div_y), (cx - 18, div_y)], fill=theme["accent"], width=3)
    d.line([(cx + 18, div_y), (cx + line_half, div_y)], fill=theme["accent"], width=3)
    d.ellipse([(cx - 6, div_y - 6), (cx + 6, div_y + 6)], fill=theme["accent"])
    y += divider_h

    # ② 中部正文
    for line in wrapped_body:
        draw_outlined_centered_text(img, y, line, body_font, theme["body"], theme["stroke"], stroke_width=7)
        y += body_step

    # ③ 底部轻互动问句
    if wrapped_q:
        y += 22
        for line in wrapped_q:
            draw_outlined_centered_text(img, y, line, q_font, theme["accent"], theme["stroke"], stroke_width=6)
            y += q_step

    # ④ 底部半透明圆角胶囊条（固定位于 y=1650 附近，避开抖音底部文案栏）
    if pill.strip():
        pb = d.textbbox((0, 0), pill, font=pill_font)
        pw = pb[2] - pb[0]
        ph = pb[3] - pb[1]
        pad_x, pad_y = 52, 22
        box_w = pw + pad_x * 2
        box_h = ph + pad_y * 2
        pill_y = max(y + 32, 1650)
        pill_y = min(pill_y, 1710)
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


def pick_unique_bgm(bgm_dirs: list[Path], duration: float, ledger: dict) -> tuple[Path, float] | None:
    """从多个 BGM 素材目录自动挑选未用过的音频/视频音轨片段，防止批量撞音乐。"""
    tracks: list[Path] = []
    for d in bgm_dirs:
        if d.exists():
            tracks.extend(
                p for p in d.rglob("*")
                if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".mp4"}
            )
    if not tracks:
        return None

    used = set(ledger.get("used_bgm", []))
    random.shuffle(tracks)
    step = math.ceil(duration + 1.0)

    for tr in tracks:
        try:
            tdur = ffprobe_duration(str(tr))
        except Exception:
            continue
        segs = []
        if tdur <= duration + 1.0:
            key = f"{tr.name}@0"
            if key not in used:
                segs.append((tr, 0.0, key))
        else:
            st = 0
            while st + duration <= tdur:
                key = f"{tr.name}@{st}"
                if key not in used:
                    segs.append((tr, float(st), key))
                st += step
        if segs:
            p, s, k = random.choice(segs)
            ledger.setdefault("used_bgm", []).append(k)
            return p, s

    # 若 BGM 池轮完一遍，随机挑一首并随机起始秒继续轮换
    tr = random.choice(tracks)
    try:
        tdur = ffprobe_duration(str(tr))
        st = random.uniform(0, max(0.0, tdur - duration))
    except Exception:
        st = 0.0
    return tr, st


def generate_gentle_ambient_wav(out_wav: Path, duration: float, seed: int) -> None:
    """无外部 BGM 时的纯离线治愈暖调和弦背景音兜底（柔和不抢眼，每条音色微变）。"""
    sr = 44100
    n_samples = int(sr * duration)
    rng = random.Random(seed)
    chords = [
        [261.63, 329.63, 392.00, 493.88],  # Cmaj7
        [220.00, 261.63, 329.63, 392.00],  # Am7
        [174.61, 220.00, 261.63, 329.63],  # Fmaj7
        [196.00, 246.94, 293.66, 392.00],  # G6
    ]
    rng.shuffle(chords)
    chord_dur = duration / len(chords)

    frames = bytearray()
    for i in range(n_samples):
        t = i / sr
        c_idx = min(int(t / chord_dur), len(chords) - 1)
        local_t = t - c_idx * chord_dur
        env = min(1.0, local_t / 0.35) * min(1.0, (chord_dur - local_t) / 0.35)
        master_env = min(1.0, t / 0.4) * min(1.0, (duration - t) / 0.8)
        val = 0.0
        for idx, freq in enumerate(chords[c_idx]):
            val += math.sin(2.0 * math.pi * freq * t) * (0.28 if idx == 0 else 0.18)
            val += math.sin(2.0 * math.pi * (freq * 2.0) * t) * 0.04
        sample = max(-1.0, min(1.0, val * env * master_env * 0.32))
        pcm = int(sample * 32767)
        frames += struct.pack("<hh", pcm, pcm)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))


def render_poster_video(
    bg_video: Path | None,
    bg_start: float,
    overlay_png: Path,
    out_mp4: Path,
    duration: float,
    bgm_audio: Path | None,
    bgm_start: float,
    bgm_volume: float,
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
        cmd += ["-stream_loop", "-1", "-ss", f"{bgm_start:.2f}", "-i", str(bgm_audio)]

    filter_complex = (
        f"[0:v]{bg_chain}[bg];"
        f"[1:v]format=rgba,fade=t=in:st=0:d=0.18:alpha=1[ov];"
        f"[bg][ov]overlay=0:0:shortest=1,format=yuv420p[vout]"
    )
    cmd += ["-filter_complex", filter_complex, "-map", "[vout]"]

    if bgm_audio is not None:
        cmd += [
            "-map", "2:a:0",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-af", f"volume={bgm_volume:.2f},afade=t=in:st=0:d=0.25,afade=t=out:st={max(0, duration-0.7):.2f}:d=0.7",
        ]
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
    parser.add_argument("--bg-dir", help="背景空镜素材池目录（不传则自动读取 ~/.yidehai-video/config.json 记住的目录 + 在线缓存）")
    parser.add_argument("--bg-source", choices=["both", "local", "online"], help="背景来源：both(本地+在线混合) / local / online")
    parser.add_argument("--bgm", help="指定背景音乐文件（支持 mp3/m4a/wav 或带音轨的 mp4）")
    parser.add_argument("--bgm-dir", help="BGM 素材池目录（不传则自动读取本机记忆目录 + 在线缓存）")
    parser.add_argument("--bgm-volume", type=float, default=0.85, help="背景音乐音量倍率（默认 0.85）")
    parser.add_argument("--silent", action="store_true", help="强制导出无声版（不加任何背景音乐）")
    parser.add_argument("--ledger", help="防重账本 JSON 路径（默认使用全局 ~/.yidehai-video/used_history.json）")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument("--force", action="store_true", help="强制覆盖同文案查重限制")
    args = parser.parse_args()

    cfg = media_manager.load_config()
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    title = job["title"].strip()
    body = job["body"]
    body_lines = body if isinstance(body, list) else [l.strip() for l in body.splitlines() if l.strip()]
    question = job.get("question", "").strip()
    pill = job.get("pill", "亿德海 · 5公斤起专人免费上门").strip()
    theme_key = job.get("theme", random.choice(list(THEMES.keys())))
    if theme_key not in THEMES:
        raise ValueError(f"未知主题 {theme_key}，可选：{list(THEMES.keys())}")

    # 1. 文案防重校验（默认使用全局账本 ~/.yidehai-video/used_history.json）
    ledger_path = Path(args.ledger or cfg["ledger_path"])
    ledger = load_ledger(ledger_path)
    copy_hash = hashlib.sha256((title + "\n" + "\n".join(body_lines)).encode("utf-8")).hexdigest()[:16]
    if copy_hash in ledger.get("used_copies", []) and not args.force:
        raise RuntimeError(f"检测到重复文案（hash={copy_hash}），已阻止重复生成！如需强制重渲请加 --force。")

    # 2. 时长微抖动（8.6~9.0s，既贴合 8.8s 标杆又避免批量文件时长完全雷同）
    duration = float(job.get("duration", round(random.uniform(8.6, 9.0), 2)))

    # 3. 背景视频与时间窗防重（融合：显式路径 / 本机记住的本地目录 / 按需下载的在线空镜缓存）
    bg_video: Path | None = None
    bg_start = 0.0
    bg_source = args.bg_source or cfg.get("bg_source", "both")
    if args.bg:
        bg_video = Path(args.bg)
    else:
        bg_dirs: list[Path] = []
        if args.bg_dir:
            bg_dirs.append(Path(args.bg_dir))
        else:
            if bg_source in ("both", "local"):
                bg_dirs.extend(Path(d) for d in cfg.get("local_bg_dirs", []))
            if bg_source in ("both", "online"):
                bg_dirs.append(Path(cfg["cache_bg_dir"]))

        picked = pick_unique_bg_segment(bg_dirs, duration, ledger)
        if picked is None and bg_source in ("both", "online"):
            # 缓存为空或全部用完时，自动按需从在线免版权源拉取新空镜
            media_manager.ensure_online_media("bg_videos", count=2, cfg=cfg)
            picked = pick_unique_bg_segment([Path(cfg["cache_bg_dir"])], duration, ledger)
        if picked is not None:
            bg_video, bg_start = picked

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = job.get("slug", f"poster-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    out_mp4 = out_dir / f"{slug}.mp4"

    bgm_audio: Path | None = None
    bgm_start = 0.0
    bgm_label = "silent"
    if not args.silent:
        if args.bgm:
            bgm_audio = Path(args.bgm)
            bgm_label = bgm_audio.name
        else:
            bgm_dirs: list[Path] = []
            if args.bgm_dir:
                bgm_dirs.append(Path(args.bgm_dir))
            else:
                bgm_dirs.extend(Path(d) for d in cfg.get("local_bgm_dirs", []))
                bgm_dirs.append(Path(cfg["cache_bgm_dir"]))
            picked_bgm = pick_unique_bgm(bgm_dirs, duration, ledger)
            if picked_bgm is None:
                media_manager.ensure_online_media("bgm_tracks", count=2, cfg=cfg)
                picked_bgm = pick_unique_bgm([Path(cfg["cache_bgm_dir"])], duration, ledger)
            if picked_bgm is not None:
                bgm_audio, bgm_start = picked_bgm
                bgm_label = f"{bgm_audio.name}@{bgm_start:.1f}s"

    with tempfile.TemporaryDirectory() as tmp:
        overlay_png = Path(tmp) / "overlay.png"
        build_overlay_png(title, body_lines, question, pill, theme_key, overlay_png)
        seed = int(hashlib.sha256(f"{copy_hash}-{datetime.now().isoformat()}".encode()).hexdigest()[:8], 16)
        if not args.silent and bgm_audio is None:
            bgm_audio = Path(tmp) / "gentle-ambient.wav"
            generate_gentle_ambient_wav(bgm_audio, duration, seed)
            bgm_label = "builtin-ambient-chord"
        render_poster_video(
            bg_video=bg_video,
            bg_start=bg_start,
            overlay_png=overlay_png,
            out_mp4=out_mp4,
            duration=duration,
            bgm_audio=bgm_audio,
            bgm_start=bgm_start,
            bgm_volume=args.bgm_volume,
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
        "bgm": bgm_label,
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
        "bgm": bgm_label,
        "copy_hash": copy_hash,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
