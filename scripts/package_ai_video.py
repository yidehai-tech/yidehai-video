#!/usr/bin/env python3
"""
亿德海团队 AI/实拍视频一键包装器（基于 HeyGen HyperFrames：https://github.com/heygen-com/hyperframes）
跨平台 macOS / Windows · 100% 脱敏 · 无品牌浮条与静态尾卡（话音落即利落收尾保完播）

支持两种输入模式：
  1. native_audio : 原生带口播音频的 AI/实拍原片（如即梦带声原片、Google Flow Omni 1.2 Flash）
  2. montage      : 多段无声视频或图片拼接（Veo 3.1 Lite 10点开场 + 本地实拍 / 即梦 5s 开场 + 本地实拍 /
                    0 点纯本地实拍视频与图片）+ Edge-TTS 干声旁白（可选混入柔和 BGM）

输出物（自动按 --organize-by-date 归档）：
  - <slug>.mp4            720x1280 竖屏成片（HeyGen HyperFrames 渲染 + 全片解码校验）
  - cover-9x16.jpg        1080x1920 竖版封面（自适应字号防裁切）
  - cover-3x4.jpg         1080x1440 小红书封面
  - qc-contact.jpg        8 帧均匀抽帧质检联系图
  - 发布文案.md & 发布信息.json
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from media_manager import DEFAULT_LEDGER_PATH, load_config, resolve_ffmpeg_tools  # noqa: E402

FORBIDDEN_TERMS = [
    "顺丰",
    "京东",
    "当场结算",
    "当场打款",
    "当场结钱",
    "即时到账",
    "立刻到账",
    "秒到账",
    "微信搜",
    "搜微信",
    "加微信",
    "看主页",
    "点主页",
    "点左下角",
    "点我头像",
    "点击头像",
    "关注我",
    "评论区扣",
    "私信我",
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def run(
    cmd: list[str],
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture,
        env=env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def find_cjk_font() -> Path:
    """跨平台查找粗体无衬线中文字体。"""
    system = platform.system().lower()
    candidates: list[Path] = []
    if system == "darwin":
        candidates = [
            Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
            Path("/System/Library/Fonts/STHeiti Medium.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        ]
    elif system == "windows":
        win_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates = [
            win_fonts / "msyhbd.ttc",
            win_fonts / "simhei.ttf",
            win_fonts / "msyh.ttc",
            win_fonts / "simsun.ttc",
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError("未找到可用的系统中文字体，请安装思源黑体或微软雅黑。")


def resolve_hyperframes_cmd() -> list[str]:
    """定位 HeyGen HyperFrames CLI（https://github.com/heygen-com/hyperframes）。"""
    hf = shutil.which("hyperframes") or shutil.which("hyperframes.cmd")
    if hf:
        return [hf]
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return [npx, "--yes", "hyperframes"]
    raise FileNotFoundError(
        "未找到 hyperframes 或 npx。请按 knowledge/00-auto-setup.md 安装 Node.js ≥ 22 与 "
        "HeyGen HyperFrames（npm_config_registry=https://registry.npmmirror.com npm install -g hyperframes）。"
    )


def ffprobe_info(ffprobe: str, media_path: Path) -> dict[str, Any]:
    proc = run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
    )
    data = json.loads(proc.stdout)
    duration = float(data["format"]["duration"])
    v_stream = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    fps = 30
    width, height = 720, 1280
    if v_stream:
        width = int(v_stream.get("width", 720))
        height = int(v_stream.get("height", 1280))
        r_rate = v_stream.get("r_frame_rate", "30/1")
        if "/" in r_rate:
            num, den = r_rate.split("/", 1)
            if float(den) > 0:
                fps = round(float(num) / float(den))
    return {
        "duration": round(duration, 2),
        "raw_duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": a_stream is not None,
    }


def check_compliance(job: dict[str, Any]) -> None:
    texts: list[str] = [
        job.get("title", ""),
        job.get("copy", ""),
        " ".join(job.get("hashtags", [])),
    ]
    for t in job.get("top_titles", []):
        texts.append(t.get("line1", ""))
        texts.append(t.get("line2", ""))
    for c in job.get("captions", []):
        texts.append(c.get("text", ""))
    cover = job.get("cover", {})
    texts.extend([cover.get("badge", ""), cover.get("line1", ""), cover.get("line2", ""), cover.get("bottom_pill", "")])
    vo = job.get("voiceover", {})
    if isinstance(vo, dict):
        texts.append(vo.get("text", ""))

    joined = "\n".join(texts)
    hits = [term for term in FORBIDDEN_TERMS if term in joined]
    if hits:
        raise ValueError(f"合规硬红线拦截！命中禁用词：{', '.join(hits)}")


def synthesize_edge_tts(text: str, out_mp3: Path, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+12%") -> None:
    edge_bin = shutil.which("edge-tts") or shutil.which("edge-tts.exe")
    if edge_bin:
        cmd = [edge_bin, "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(out_mp3)]
    else:
        cmd = [sys.executable, "-m", "edge_tts", "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(out_mp3)]
    run(cmd)


def prepare_native_audio_assets(
    ffmpeg: str, ffprobe: str, job: dict[str, Any], assets_dir: Path
) -> tuple[float, int, Path]:
    raw_video = Path(job["raw_video"]).expanduser().resolve()
    if not raw_video.is_file():
        raise FileNotFoundError(f"原片不存在：{raw_video}")
    info = ffprobe_info(ffprobe, raw_video)
    duration = float(job.get("duration") or info["raw_duration"])
    fps = int(job.get("fps") or info["fps"] or 30)

    footage_dst = assets_dir / "footage.mp4"
    audio_dst = assets_dir / "audio.wav"

    run([
        ffmpeg, "-y", "-v", "error", "-i", str(raw_video), "-an",
        "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1",
        "-r", str(fps), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
        str(footage_dst),
    ])
    if info["has_audio"]:
        run([
            ffmpeg, "-y", "-v", "error", "-i", str(raw_video), "-vn",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(audio_dst),
        ])
    else:
        run([
            ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", f"{duration:.2f}", "-c:a", "pcm_s16le", str(audio_dst),
        ])
    return round(duration, 2), fps, footage_dst


def prepare_montage_assets(
    ffmpeg: str, ffprobe: str, job: dict[str, Any], assets_dir: Path
) -> tuple[float, int, Path, list[str]]:
    vo = job.get("voiceover") or {}
    fps = int(job.get("fps") or 30)
    audio_dst = assets_dir / "audio.wav"
    footage_dst = assets_dir / "footage.mp4"
    used_names: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        if vo.get("text"):
            mp3_path = tmp_dir / "vo.mp3"
            synthesize_edge_tts(
                vo["text"],
                mp3_path,
                voice=vo.get("voice", "zh-CN-XiaoxiaoNeural"),
                rate=vo.get("rate", "+12%"),
            )
            run([
                ffmpeg, "-y", "-v", "error", "-i", str(mp3_path),
                "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(audio_dst),
            ])
            audio_info = ffprobe_info(ffprobe, audio_dst)
            target_dur = round(float(job.get("duration") or (audio_info["raw_duration"] + 0.12)), 2)
        else:
            target_dur = round(float(job.get("duration") or 12.0), 2)
            run([
                ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-t", f"{target_dur:.2f}", "-c:a", "pcm_s16le", str(audio_dst),
            ])

        clips = job.get("clips", [])
        if not clips:
            raise ValueError("montage 模式必须提供非空的 clips 列表。")

        fixed_total = sum(float(c["duration"]) for c in clips if "duration" in c)
        missing_count = sum(1 for c in clips if "duration" not in c)
        auto_dur = max(1.5, (target_dur - fixed_total) / missing_count) if missing_count > 0 else 0.0

        seg_paths: list[Path] = []
        for idx, clip in enumerate(clips):
            c_path = Path(clip["path"]).expanduser().resolve()
            if not c_path.is_file():
                raise FileNotFoundError(f"素材文件不存在：{c_path}")
            used_names.append(c_path.name)
            c_dur = float(clip.get("duration", auto_dur))
            seg_out = tmp_dir / f"seg_{idx:02d}.mp4"

            if c_path.suffix.lower() in IMAGE_EXTS:
                # 静态图片自动做轻微 Ken Burns 缓慢推镜，避免画面死板
                frames = max(int(round(c_dur * fps)), 30)
                vf = (
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                    f"zoompan=z='min(zoom+0.0008,1.08)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280:fps={fps},"
                    "setsar=1"
                )
                run([
                    ffmpeg, "-y", "-v", "error", "-loop", "1", "-t", f"{c_dur:.2f}",
                    "-i", str(c_path), "-an", "-vf", vf,
                    "-r", str(fps), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    str(seg_out),
                ])
            else:
                c_start = float(clip.get("start", 0.0))
                run([
                    ffmpeg, "-y", "-v", "error", "-ss", f"{c_start:.2f}", "-t", f"{c_dur:.2f}",
                    "-i", str(c_path), "-an",
                    "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1",
                    "-r", str(fps), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    str(seg_out),
                ])
            seg_paths.append(seg_out)

        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in seg_paths) + "\n",
            encoding="utf-8",
        )
        run([
            ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-t", f"{target_dur:.2f}",
            "-c", "copy", str(footage_dst),
        ])

    return target_dur, fps, footage_dst, used_names


def auto_captions_from_text(text: str, duration: float) -> list[dict[str, Any]]:
    """若未显式提供精确时间戳字幕，按句长自动均分，每条 ≤ 15 字。"""
    import re
    raw_parts = [p.strip() for p in re.split(r"[，。！？、；\n]+", text) if p.strip()]
    chunks: list[str] = []
    for p in raw_parts:
        while len(p) > 15:
            chunks.append(p[:14])
            p = p[14:]
        if p:
            chunks.append(p)
    if not chunks:
        return []
    total_chars = sum(len(c) for c in chunks)
    cur = 0.0
    out: list[dict[str, Any]] = []
    for idx, ch in enumerate(chunks):
        seg = round((len(ch) / total_chars) * duration, 2)
        if idx == len(chunks) - 1:
            seg = round(max(0.4, duration - cur), 2)
        out.append({"start": round(cur, 2), "duration": seg, "text": ch, "yellow": idx == 0})
        cur += seg
    return out


def build_hyperframes_html(job: dict[str, Any], duration: float, font_ext: str) -> str:
    """生成符合 HeyGen HyperFrames 规范的单工程 HTML（无品牌浮条、无静态尾卡）。"""
    slug = job["slug"]
    top_blocks: list[str] = []
    for idx, t in enumerate(job.get("top_titles", [])):
        t_start = float(t.get("start", 0.0))
        t_dur = float(t.get("duration", duration))
        l1 = html.escape(t.get("line1", ""))
        l2 = html.escape(t.get("line2", ""))
        l1_size = t.get("line1_size")
        l2_size = t.get("line2_size") or (42 if len(t.get("line2", "")) >= 12 else None)
        l1_style = f' style="font-size: {l1_size}px;"' if l1_size else ""
        l2_style = f' style="font-size: {l2_size}px;"' if l2_size else ""
        top_blocks.append(
            f'  <div id="top{idx}" class="clip top-title" data-start="{t_start:.2f}" '
            f'data-duration="{t_dur:.2f}" data-track-index="1">\n'
            f"    <div{l1_style}>{l1}</div>\n"
            f'    <div class="yellow"{l2_style}>{l2}</div>\n'
            f"  </div>"
        )

    captions = job.get("captions") or []
    if not captions and isinstance(job.get("voiceover"), dict) and job["voiceover"].get("text"):
        captions = auto_captions_from_text(job["voiceover"]["text"], duration)

    sub_blocks: list[str] = []
    for idx, c in enumerate(captions):
        c_start = float(c["start"])
        c_dur = float(c["duration"])
        cls = "clip caption yellow" if c.get("yellow") else "clip caption"
        c_text = html.escape(c["text"])
        sub_blocks.append(
            f'  <div id="sub{idx}" class="{cls}" data-start="{c_start:.2f}" '
            f'data-duration="{c_dur:.2f}" data-track-index="2">{c_text}</div>'
        )

    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face {{
  font-family: Story;
  src: url(assets/font{font_ext});
}}
html, body {{
  margin: 0;
  width: 100%;
  height: 100%;
  background: #000;
}}
#root {{
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  font-family: Story, "PingFang SC", "Microsoft YaHei", sans-serif;
}}
video {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}}
.top-title {{
  position: absolute;
  left: 20px;
  top: 72px;
  width: 680px;
  text-align: center;
  font-size: 48px;
  font-weight: 800;
  line-height: 1.35;
  color: #ffffff;
  paint-order: stroke fill;
  -webkit-text-stroke: 7px #111111;
  text-shadow: 0 4px 8px rgba(0,0,0,0.85);
}}
.yellow {{
  color: #ffe332;
}}
.caption {{
  position: absolute;
  left: 20px;
  top: 1020px;
  width: 680px;
  text-align: center;
  font-size: 38px;
  font-weight: 700;
  line-height: 1.4;
  color: #ffffff;
  paint-order: stroke fill;
  -webkit-text-stroke: 7px #111111;
  text-shadow: 0 4px 8px rgba(0,0,0,0.85);
  white-space: pre-line;
}}
</style>
</head>
<body>
<div id="root" data-composition-id="{html.escape(slug)}" data-width="720" data-height="1280" data-duration="{duration:.2f}" data-fps="30">
  <video id="footage" class="clip" src="assets/footage.mp4" data-has-audio="false" data-start="0" data-duration="{duration:.2f}" data-track-index="0"></video>

{chr(10).join(top_blocks)}

{chr(10).join(sub_blocks)}

  <audio id="audio" src="assets/audio.wav" data-start="0" data-duration="{duration:.2f}" data-track-index="3" data-volume="1.0"></audio>
</div>

<script>
const t = gsap.timeline({{ paused: true }});
t.to({{}}, {{ duration: {duration:.2f} }});
window.__timelines = {{ "{html.escape(slug)}": t }};
</script>
</body>
</html>
"""


def generate_covers(
    ffmpeg: str, source_video: Path, output_dir: Path, cover_cfg: dict[str, Any], font_path: Path
) -> tuple[Path, Path]:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    frame_sec = float(cover_cfg.get("frame_sec", 1.2))
    line1 = cover_cfg.get("line1", "")
    line2 = cover_cfg.get("line2", "")
    bottom_pill = cover_cfg.get("bottom_pill", "")

    with tempfile.TemporaryDirectory() as tmp:
        raw_frame = Path(tmp) / "cover_frame.png"
        run([
            ffmpeg, "-y", "-v", "error", "-ss", f"{frame_sec:.2f}",
            "-i", str(source_video), "-frames:v", "1", str(raw_frame),
        ])
        base_img = Image.open(raw_frame).convert("RGBA")

    def fit_font(text: str, start_size: int, max_width: int, min_size: int = 40):
        size = start_size
        while size >= min_size:
            f = ImageFont.truetype(str(font_path), size)
            bbox = f.getbbox(text)
            if (bbox[2] - bbox[0]) <= max_width:
                return f
            size -= 2
        return ImageFont.truetype(str(font_path), min_size)

    def render_one(width: int, height: int, out_path: Path) -> None:
        src_w, src_h = base_img.size
        target_ratio = width / height
        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            new_h = height
            new_w = int(round(src_w * (height / src_h)))
        else:
            new_w = width
            new_h = int(round(src_h * (width / src_w)))
        resized = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - width) // 2
        top = 0 if (height / width) < 1.5 else (new_h - height) // 2
        canvas = resized.crop((left, top, left + width, top + height))

        grad = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grad)
        top_h = int(height * 0.34)
        for y in range(top_h):
            alpha = int(175 * (1 - y / top_h) ** 1.4)
            gdraw.line([(0, y), (width, y)], fill=(8, 16, 14, alpha))
        bot_h = int(height * 0.22)
        for i in range(bot_h):
            y = height - 1 - i
            alpha = int(175 * (1 - i / bot_h) ** 1.4)
            gdraw.line([(0, y), (width, y)], fill=(8, 16, 14, alpha))
        canvas = Image.alpha_composite(canvas, grad)
        draw = ImageDraw.Draw(canvas)

        max_w = int(width * 0.88)
        y_cursor = int(height * 0.14)
        for idx, text in enumerate([line1, line2]):
            if not text:
                continue
            f = fit_font(text, 108 if height >= 1800 else 96, max_w)
            bbox = f.getbbox(text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (width - tw) // 2
            color = (255, 255, 255, 255) if idx == 0 else (255, 227, 50, 255)
            draw.text((tx, y_cursor), text, font=f, fill=color, stroke_width=8, stroke_fill=(15, 15, 15, 255))
            y_cursor += th + 28

        if bottom_pill:
            pf = fit_font(bottom_pill, 40, int(width * 0.82), min_size=26)
            pb = pf.getbbox(bottom_pill)
            pw, ph = pb[2] - pb[0], pb[3] - pb[1]
            box_w, box_h = pw + 60, ph + 32
            bx, by = (width - box_w) // 2, int(height * 0.84)
            draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=box_h // 2, fill=(0, 0, 0, 150))
            draw.text((bx + 30, by + 12), bottom_pill, font=pf, fill=(255, 245, 210, 255))

        canvas.convert("RGB").save(out_path, "JPEG", quality=92)

    c916 = output_dir / "cover-9x16.jpg"
    c34 = output_dir / "cover-3x4.jpg"
    render_one(1080, 1920, c916)
    render_one(1080, 1440, c34)
    return c916, c34


def generate_qc_contact(ffmpeg: str, video_path: Path, duration: float, out_path: Path) -> None:
    from PIL import Image  # type: ignore

    times = [max(0.05, min(duration - 0.1, duration * r)) for r in (0.04, 0.16, 0.30, 0.44, 0.58, 0.72, 0.86, 0.96)]
    thumbs: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            p = Path(tmp) / f"f{i}.png"
            run([
                ffmpeg, "-y", "-v", "error", "-ss", f"{t:.2f}",
                "-i", str(video_path), "-frames:v", "1", str(p),
            ])
            im = Image.open(p).convert("RGB").resize((270, 480), Image.Resampling.LANCZOS)
            thumbs.append(im)
    sheet = Image.new("RGB", (270 * 4, 480 * 2), (16, 16, 16))
    for idx, im in enumerate(thumbs):
        sheet.paste(im, ((idx % 4) * 270, (idx // 4) * 480))
    sheet.save(out_path, "JPEG", quality=90)


def record_used_footage(names: list[str]) -> None:
    if not names:
        return
    cfg = load_config()
    ledger_path = Path(cfg.get("ledger_path") or DEFAULT_LEDGER_PATH)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if ledger_path.exists():
        try:
            data = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    used = list(data.get("used_footage", []))
    for n in names:
        if n not in used:
            used.append(n)
    data["used_footage"] = used
    ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海 AI/实拍视频一键包装器（HeyGen HyperFrames · 无品牌浮条）")
    parser.add_argument("--job", required=True, help="任务 JSON 路径")
    parser.add_argument("--out-dir", default="outputs", help="输出根目录")
    parser.add_argument("--organize-by-date", action="store_true", help="按 YYYY-MM-DD/YYYYMMDD-HHMMSS-<slug>/ 归档")
    parser.add_argument("--quality", choices=["draft", "looks", "delivery"], default="delivery", help="HyperFrames 渲染画质")
    args = parser.parse_args()

    job = json.loads(Path(args.job).expanduser().read_text(encoding="utf-8"))
    check_compliance(job)

    ffmpeg, ffprobe = resolve_ffmpeg_tools()
    hf_cmd = resolve_hyperframes_cmd()
    font_path = find_cjk_font()

    slug = job["slug"]
    out_root = Path(args.out_dir).expanduser().resolve()
    if args.organize_by_date:
        day = time.strftime("%Y-%m-%d")
        ts = time.strftime("%Y%m%d-%H%M%S")
        tag = job.get("format_label") or ("实拍混剪" if job.get("mode") == "montage" else "AI视频")
        out_dir = out_root / day / f"{ts}-{tag}-{slug}"
    else:
        out_dir = out_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    proj_dir = out_dir / "hf-project"
    assets_dir = proj_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    font_dst = assets_dir / f"font{font_path.suffix}"
    shutil.copy2(font_path, font_dst)

    mode = job.get("mode", "native_audio")
    used_footage: list[str] = []
    if mode == "montage":
        duration, fps, footage_path, used_footage = prepare_montage_assets(ffmpeg, ffprobe, job, assets_dir)
    else:
        duration, fps, footage_path = prepare_native_audio_assets(ffmpeg, ffprobe, job, assets_dir)

    index_html = build_hyperframes_html(job, duration, font_path.suffix)
    (proj_dir / "index.html").write_text(index_html, encoding="utf-8")

    # 1) HeyGen HyperFrames check & render
    env = os.environ.copy()
    env.setdefault("npm_config_registry", "https://registry.npmmirror.com")
    run(hf_cmd + ["check", "--json"], cwd=proj_dir, check=False, env=env)
    final_mp4 = out_dir / f"{slug}.mp4"
    run(hf_cmd + ["render", "--quality", args.quality, "-o", str(final_mp4)], cwd=proj_dir, env=env)

    # 2) 全片解码校验
    run([ffmpeg, "-v", "error", "-i", str(final_mp4), "-f", "null", "-"])

    # 3) 双封面 + 8 帧质检图
    c916, c34 = generate_covers(ffmpeg, footage_path, out_dir, job.get("cover", {}), font_path)
    qc_img = out_dir / "qc-contact.jpg"
    generate_qc_contact(ffmpeg, final_mp4, duration, qc_img)

    # 4) 发布文案与元数据
    hashtags = " ".join(job.get("hashtags", ["#旧衣回收", "#断舍离", "#亿德海"]))
    ai_note = "⚠️ 发布提醒：本片含 AI 生成画面/配音，请按各平台要求勾选「AI 生成」声明。" if job.get("is_ai", True) else ""
    copy_md = (
        f"# {job.get('title', slug)}\n\n"
        f"{job.get('copy', '')}\n\n"
        f"{hashtags}\n\n"
        f"{ai_note}\n"
    )
    (out_dir / "发布文案.md").write_text(copy_md, encoding="utf-8")
    meta = {
        "slug": slug,
        "mode": mode,
        "duration": duration,
        "fps": fps,
        "video": str(final_mp4),
        "cover_9x16": str(c916),
        "cover_3x4": str(c34),
        "qc_contact": str(qc_img),
        "used_footage": used_footage,
    }
    (out_dir / "发布信息.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    record_used_footage(used_footage)

    print(json.dumps({"ok": True, **meta}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
