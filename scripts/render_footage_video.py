#!/usr/bin/env python3
"""
亿德海本地实拍素材库专用离线出片引擎（0 积分 · 纯 Python + Pillow + FFmpeg + Edge-TTS，无需 Node/浏览器）

专为海量本地业务实拍视频与客户照片打造 2 大高转化竖屏形态：
  1. fastcut（实拍快剪）：6–8 个 1.2–2.0s 快节奏短镜头（视频+照片 Ken Burns 推镜混剪）+ 顶部双行钩子大字 + 底部卡点字幕 + -14 LUFS 清晰旁白 + 18% 归一化 BGM
  2. before_after（前后对比片）：上下双屏对比（上屏「清理前」vs 下屏「清空后」+ 精致主题分隔条与状态徽章）+ 顶部钩子大字 + 底部字幕 + 清晰旁白 + BGM

统一规范：
  - 合规硬红线拦截（0 禁用词，严禁当面称重/现场结算/快递品牌/违规引流）
  - 无底部品牌浮条、无全屏静态尾卡，话音一落利落收尾
  - 缺 BGM 硬拦截（除非显式 --silent），绝不出无声残缺作品
  - 同步输出：1080x1920 MP4 + 9:16 封面 + 3:4 小红书封面 + 8 帧质检图 + 发布文案.md + 防重账本回写
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import media_manager  # noqa: E402
import render_poster  # noqa: E402
import task_tracker  # noqa: E402

WIDTH = 1080
HEIGHT = 1920
FPS = 30
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"命令执行失败（exit={proc.returncode}）：{' '.join(cmd[:6])}...\n{proc.stderr[-600:]}")
    return proc


def ffprobe_duration(ffprobe: str, path: Path) -> float:
    out = run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]).stdout.strip()
    return float(out)


def synthesize_edge_tts(text: str, out_mp3: Path, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+12%") -> None:
    edge_bin = shutil.which("edge-tts") or shutil.which("edge-tts.exe")
    cmd = (
        [edge_bin, "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(out_mp3)]
        if edge_bin else
        [sys.executable, "-m", "edge_tts", "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(out_mp3)]
    )
    run(cmd)


def split_caption_clauses(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[，。！？；\n]+", text) if p.strip()]
    return parts or [text.strip()]


def render_clip_segment(
    ffmpeg: str,
    ffprobe: str,
    src_path: Path,
    out_mp4: Path,
    dur: float,
    target_w: int,
    target_h: int,
    start: float = 0.0,
) -> None:
    """将单段视频或静态图片转为标准 30fps 无声片段（图片自动做轻微 Ken Burns 缓慢推镜）。"""
    ext = src_path.suffix.lower()
    if ext in IMAGE_EXTS:
        frames = max(int(round(dur * FPS)), 15)
        pre_w = int(target_w * 1.12) // 2 * 2
        pre_h = int(target_h * 1.12) // 2 * 2
        vf = (
            f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=increase,crop={pre_w}:{pre_h},"
            f"zoompan=z='min(zoom+0.0012,1.10)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={target_w}x{target_h}:fps={FPS},"
            "setsar=1,format=yuv420p"
        )
        run([
            ffmpeg, "-y", "-v", "error",
            "-i", str(src_path), "-an", "-vf", vf,
            "-t", f"{dur:.2f}", "-r", str(FPS), "-video_track_timescale", "30000",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(out_mp4),
        ])
    else:
        vdur = ffprobe_duration(ffprobe, src_path)
        cmd = [ffmpeg, "-y", "-v", "error"]
        if vdur < dur + start:
            cmd += ["-stream_loop", "-1"]
        cmd += [
            "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src_path), "-an",
            "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},fps={FPS},setsar=1,format=yuv420p",
            "-r", str(FPS), "-video_track_timescale", "30000",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(out_mp4),
        ]
        run(cmd)


def draw_centered_outlined(
    img: Image.Image,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    stroke_fill: tuple[int, int, int, int] = (18, 20, 24, 255),
    stroke_width: int = 7,
) -> int:
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (WIDTH - tw) // 2 - bbox[0]

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(
        (x, y + 4), text, font=font,
        fill=(0, 0, 0, 160), stroke_width=stroke_width + 2, stroke_fill=(0, 0, 0, 160),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
    img.alpha_composite(shadow)

    ImageDraw.Draw(img).text(
        (x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
    )
    return th


def build_top_overlay_png(
    title_line1: str,
    title_line2: str,
    out_png: Path,
    mode: str,
    before_label: str = "清理前 · 衣柜塞爆",
    after_label: str = "清空后 · 装袋待上门",
) -> None:
    font_path, font_idx = render_poster.find_chinese_bold_font()
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 顶部护眼暗渐变（y=0..340），确保白色/黄色大标题在任何实拍画面上清晰可读
    for row in range(340):
        alpha = int(155 * (1.0 - row / 340.0))
        draw.line([(0, row), (WIDTH, row)], fill=(8, 12, 16, alpha))

    f1 = render_poster.load_font(font_path, font_idx, 78)
    f2 = render_poster.load_font(font_path, font_idx, 60)
    y = 110
    if title_line1:
        h1 = draw_centered_outlined(img, y, title_line1, f1, (245, 200, 66, 255), stroke_width=7)
        y += h1 + 18
    if title_line2:
        draw_centered_outlined(img, y, title_line2, f2, (255, 255, 255, 255), stroke_width=6)

    if mode == "before_after":
        mid_y = HEIGHT // 2
        # 中间精致分割线
        draw.rectangle([(0, mid_y - 4), (WIDTH, mid_y + 4)], fill=(245, 200, 66, 240))
        badge_font = render_poster.load_font(font_path, font_idx, 40)

        def _draw_badge(label: str, by: int, bg_rgba: tuple[int, int, int, int], fg_rgba: tuple[int, int, int, int]) -> None:
            bb = draw.textbbox((0, 0), label, font=badge_font)
            bw, bh = bb[2] - bb[0], bb[3] - bb[1]
            px, py = 30, 14
            x0, y0 = 42, by
            draw.rounded_rectangle([(x0, y0), (x0 + bw + px * 2, y0 + bh + py * 2)], radius=24, fill=bg_rgba)
            draw.text((x0 + px - bb[0], y0 + py - bb[1]), label, font=badge_font, fill=fg_rgba)

        _draw_badge(before_label, 340, (24, 24, 30, 205), (255, 224, 130, 255))
        _draw_badge(after_label, mid_y + 28, (22, 118, 68, 225), (255, 255, 255, 255))

    img.save(out_png, "PNG")


def build_caption_png(text: str, out_png: Path) -> None:
    font_path, font_idx = render_poster.find_chinese_bold_font()
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = render_poster.load_font(font_path, font_idx, 56)
    lines = render_poster.wrap_line(draw, text, f, WIDTH - 120)[:2]
    y = 1490 if len(lines) == 1 else 1445
    for ln in lines:
        h = draw_centered_outlined(img, y, ln, f, (255, 255, 255, 255), stroke_width=6)
        y += h + 14
    img.save(out_png, "PNG")


def record_used_footage(names: list[str], cfg: dict) -> None:
    if not names:
        return
    ledger_path = Path(cfg.get("ledger_path") or media_manager.DEFAULT_LEDGER_PATH)
    with media_manager.file_lock(ledger_path.with_suffix(".lock"), timeout=15.0):
        data = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
        used = list(data.get("used_footage", []))
        for n in names:
            if n not in used:
                used.append(n)
        data["used_footage"] = used
        media_manager.atomic_write_json(ledger_path, data)


def export_covers_and_qc(ffmpeg: str, mp4_path: Path, duration: float, out_dir: Path) -> tuple[Path, Path, Path]:
    c916 = out_dir / "cover-9x16.jpg"
    c34 = out_dir / "cover-3x4.jpg"
    qc = out_dir / "qc-contact.jpg"
    sample_t = min(1.8, max(0.4, duration * 0.25))
    run([ffmpeg, "-y", "-v", "error", "-ss", f"{sample_t:.2f}", "-i", str(mp4_path), "-frames:v", "1", "-q:v", "2", str(c916)])
    run([ffmpeg, "-y", "-v", "error", "-i", str(c916), "-vf", "crop=1080:1440:0:170", "-q:v", "2", str(c34)])
    fps_expr = max(0.3, 8.0 / max(duration, 1.0))
    run([
        ffmpeg, "-y", "-v", "error", "-i", str(mp4_path),
        "-vf", f"fps={fps_expr:.3f},scale=270:480,tile=4x2",
        "-frames:v", "1", "-q:v", "3", str(qc),
    ])
    return c916, c34, qc


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海本地素材库离线出片引擎（实拍快剪 fastcut / 前后对比 before_after）")
    parser.add_argument("--mode", choices=["fastcut", "before_after"], required=True, help="出片形态：fastcut（实拍快剪）或 before_after（前后对比片）")
    parser.add_argument("--job", required=True, help="任务配置 JSON 路径")
    parser.add_argument("--out-dir", default="outputs", help="输出根目录")
    parser.add_argument("--organize-by-date", action="store_true", help="按日期与中文形态子目录归档")
    parser.add_argument("--bgm-dir", default="", help="可选：指定 BGM 目录")
    parser.add_argument("--silent", action="store_true", help="显式输出纯人声干声版（不加 BGM）")
    args = parser.parse_args()

    cfg = media_manager.load_config()
    ffmpeg, ffprobe = media_manager.resolve_ffmpeg_tools()
    job: dict[str, Any] = json.loads(Path(args.job).expanduser().read_text(encoding="utf-8"))

    # 1) 合规硬红线拦截
    title_l1 = str(job.get("title_line1") or job.get("title") or "").strip()
    title_l2 = str(job.get("title_line2") or "").strip()
    vo_text = str((job.get("voiceover") or {}).get("text") or job.get("voiceover_text") or "").strip()
    publish_copy = str(job.get("copy") or job.get("publish_copy") or "").strip()
    before_label = str(job.get("before_label") or "清理前 · 衣柜塞爆").strip()
    after_label = str(job.get("after_label") or "清空后 · 装袋待上门").strip()
    hits = media_manager.check_forbidden_terms([title_l1, title_l2, vo_text, publish_copy, before_label, after_label])
    if hits:
        raise ValueError(f"合规硬红线拦截！命中禁用词：{', '.join(hits)}")
    if not vo_text:
        raise ValueError("必须提供非空的 voiceover.text（或 voiceover_text）口播文案。")

    # 2) 输出目录准备
    slug = media_manager.sanitize_slug(job.get("slug", args.mode), fallback=args.mode)
    out_root = Path(args.out_dir).expanduser().resolve()
    mode_zh = "实拍快剪" if args.mode == "fastcut" else "前后对比片"
    if args.organize_by_date:
        day = time.strftime("%Y-%m-%d")
        ts = time.strftime("%Y%m%d-%H%M%S")
        out_dir = media_manager.safe_child_path(out_root, day, f"{ts}-{mode_zh}-{slug}")
    else:
        out_dir = media_manager.safe_child_path(out_root, slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    final_mp4 = media_manager.safe_child_path(out_dir, f"{slug}.mp4")
    task_id = task_tracker.safe_start_task(
        track=args.mode,
        title=f"{title_l1} {title_l2}".strip() or slug,
        slug=slug,
        out_dir=str(out_dir),
        copy_text=publish_copy or vo_text,
    )

    try:
        # 3) 校验并挑选 BGM（非 --silent 时缺源硬拦截）
        bgm_src: Path | None = None
        bgm_start = 0.0
        bgm_label = "dry-voice-by-request"
        ledger_path = Path(cfg.get("ledger_path") or media_manager.DEFAULT_LEDGER_PATH)
        ledger = render_poster.load_ledger(ledger_path)
        want_silent = bool(args.silent or job.get("silent"))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            voice_mp3 = tmp_dir / "voice.mp3"
            vo_cfg = job.get("voiceover") or {}
            synthesize_edge_tts(
                vo_text,
                voice_mp3,
                voice=str(vo_cfg.get("voice") or "zh-CN-XiaoxiaoNeural"),
                rate=str(vo_cfg.get("rate") or "+12%"),
            )
            vo_dur = ffprobe_duration(ffprobe, voice_mp3)
            duration = round(max(6.0, float(job.get("duration") or (vo_dur + 0.25))), 2)

            if not want_silent:
                bgm_dirs = [Path(args.bgm_dir)] if args.bgm_dir else (
                    [Path(cfg["cache_bgm_dir"])] + [Path(d) for d in cfg.get("local_bgm_dirs", [])]
                )
                picked_bgm = render_poster.pick_unique_bgm(bgm_dirs, duration, ledger)
                if picked_bgm is None:
                    media_manager.ensure_online_media("bgm_tracks", count=2, cfg=cfg)
                    picked_bgm = render_poster.pick_unique_bgm([Path(cfg["cache_bgm_dir"])], duration, ledger)
                if picked_bgm is None:
                    raise RuntimeError(
                        "【硬拦截：缺少真实背景音乐源】未加 --silent 且本机无可用 BGM，严禁输出残缺成品。"
                        "请配置 --add-bgm-dir 或 --set-jamendo-id，或显式传 --silent。"
                    )
                bgm_src, bgm_start = picked_bgm
                bgm_label = f"{bgm_src.name}@{bgm_start:.1f}s(loudnorm+18%)"

            # 4) 组装底座画面流
            base_video = tmp_dir / "base.mp4"
            used_names: list[str] = []

            if args.mode == "fastcut":
                clips = job.get("clips") or []
                if len(clips) < 3:
                    raise ValueError("fastcut 模式 job.clips 至少需要 3 个素材片段（推荐 6–8 个 1.2–2.0s 快切镜头）。")
                seg_dur = round(duration / len(clips), 3)
                seg_files: list[Path] = []
                for idx, item in enumerate(clips):
                    c_path = Path(item["path"] if isinstance(item, dict) else str(item)).expanduser().resolve()
                    if not c_path.is_file():
                        raise FileNotFoundError(f"素材文件不存在：{c_path}")
                    used_names.append(c_path.name)
                    c_start = float(item.get("start", 0.0)) if isinstance(item, dict) else 0.0
                    c_dur = float(item.get("duration", seg_dur)) if isinstance(item, dict) else seg_dur
                    seg_out = tmp_dir / f"seg_{idx:02d}.mp4"
                    render_clip_segment(ffmpeg, ffprobe, c_path, seg_out, c_dur, WIDTH, HEIGHT, start=c_start)
                    seg_files.append(seg_out)
                concat_txt = tmp_dir / "concat.txt"
                concat_txt.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_files) + "\n", encoding="utf-8")
                run([
                    ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-vf", f"fps={FPS},setpts=PTS-STARTPTS,format=yuv420p",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    str(base_video),
                ])
            else:
                before_item = job.get("before")
                after_item = job.get("after")
                if not before_item or not after_item:
                    raise ValueError("before_after 模式必须在 job.json 中同时提供 before 与 after 素材路径。")
                b_path = Path(before_item["path"] if isinstance(before_item, dict) else str(before_item)).expanduser().resolve()
                a_path = Path(after_item["path"] if isinstance(after_item, dict) else str(after_item)).expanduser().resolve()
                if not b_path.is_file() or not a_path.is_file():
                    raise FileNotFoundError(f"对比素材不存在：before={b_path}, after={a_path}")
                used_names.extend([b_path.name, a_path.name])
                top_seg = tmp_dir / "top_before.mp4"
                bot_seg = tmp_dir / "bot_after.mp4"
                render_clip_segment(ffmpeg, ffprobe, b_path, top_seg, duration, WIDTH, HEIGHT // 2, start=float(before_item.get("start", 0.0)) if isinstance(before_item, dict) else 0.0)
                render_clip_segment(ffmpeg, ffprobe, a_path, bot_seg, duration, WIDTH, HEIGHT // 2, start=float(after_item.get("start", 0.0)) if isinstance(after_item, dict) else 0.0)
                run([
                    ffmpeg, "-y", "-v", "error", "-i", str(top_seg), "-i", str(bot_seg),
                    "-filter_complex", "[0:v][1:v]vstack=inputs=2[v]",
                    "-map", "[v]", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    str(base_video),
                ])

            # 5) 将顶部标题 + 每句卡点字幕用 Pillow 预合成为单路互斥叠加流（O(1) 单 overlay，彻底杜绝多路 framesync 死锁）
            top_png = tmp_dir / "top_overlay.png"
            build_top_overlay_png(title_l1, title_l2, top_png, mode=args.mode, before_label=before_label, after_label=after_label)
            top_img = Image.open(top_png).convert("RGBA")

            clauses = split_caption_clauses(vo_text)
            total_chars = max(1, sum(len(c) for c in clauses))
            ov_concat_lines: list[str] = []
            cursor = 0.0
            last_png = top_png
            for idx, clause in enumerate(clauses):
                c_len = max(0.5, (len(clause) / total_chars) * vo_dur)
                c_png = tmp_dir / f"cap_{idx:02d}.png"
                build_caption_png(clause, c_png)
                merged = top_img.copy()
                merged.alpha_composite(Image.open(c_png).convert("RGBA"))
                ov_png = tmp_dir / f"ov_{idx:02d}.png"
                merged.save(ov_png, "PNG")
                ov_concat_lines.append(f"file '{ov_png.as_posix()}'")
                ov_concat_lines.append(f"duration {c_len:.3f}")
                cursor += c_len
                last_png = ov_png
            if cursor < duration:
                ov_concat_lines.append(f"file '{top_png.as_posix()}'")
                ov_concat_lines.append(f"duration {max(0.1, duration - cursor):.3f}")
                last_png = top_png
            ov_concat_lines.append(f"file '{last_png.as_posix()}'")
            ov_concat_txt = tmp_dir / "ov_concat.txt"
            ov_concat_txt.write_text("\n".join(ov_concat_lines) + "\n", encoding="utf-8")

            # 6) 合成最终视频（先将音频独立混音，再单路合成视频，彻底杜绝复杂滤镜图音画同步死锁）
            mixed_audio = tmp_dir / "mixed_audio.m4a"
            fade_out_st = max(0.0, duration - 0.9)
            if bgm_src is not None:
                bgm_dur = ffprobe_duration(ffprobe, bgm_src)
                acmd = [ffmpeg, "-y", "-v", "error", "-i", str(voice_mp3)]
                if bgm_dur < duration + bgm_start:
                    acmd += ["-stream_loop", "-1"]
                acmd += [
                    "-ss", f"{bgm_start:.2f}", "-t", f"{duration:.2f}", "-i", str(bgm_src),
                    "-filter_complex",
                    f"[0:a]aresample=48000,loudnorm=I=-14:TP=-1.5:LRA=7,apad=whole_dur={duration:.2f},atrim=0:{duration:.2f}[va];"
                    f"[1:a]atrim=0:{duration:.2f},asetpts=PTS-STARTPTS,aresample=48000,loudnorm=I=-16:TP=-2:LRA=11,afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_st:.2f}:d=0.9,volume=0.18[ba];"
                    f"[va][ba]amix=inputs=2:normalize=0:duration=first:dropout_transition=0,alimiter=limit=0.95[aout]",
                    "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.2f}", str(mixed_audio),
                ]
                run(acmd)
            else:
                run([
                    ffmpeg, "-y", "-v", "error", "-i", str(voice_mp3),
                    "-af", f"aresample=48000,loudnorm=I=-14:TP=-1.5:LRA=7,apad=whole_dur={duration:.2f},atrim=0:{duration:.2f},alimiter=limit=0.95",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.2f}", str(mixed_audio),
                ])

            run([
                ffmpeg, "-y", "-v", "error",
                "-i", str(base_video),
                "-f", "concat", "-safe", "0", "-i", str(ov_concat_txt),
                "-i", str(mixed_audio),
                "-filter_complex", f"[1:v]fps={FPS},format=rgba[ov];[0:v][ov]overlay=0:0:shortest=1,format=yuv420p[vout]",
                "-map", "[vout]", "-map", "2:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "copy",
                "-t", f"{duration:.2f}", "-movflags", "+faststart",
                str(final_mp4),
            ])

        # 7) 全片校验 + 双封面 + 8 帧质检 + 记账
        run([ffmpeg, "-v", "error", "-i", str(final_mp4), "-f", "null", "-"])
        c916, c34, qc = export_covers_and_qc(ffmpeg, final_mp4, duration, out_dir)
    except Exception as exc:
        task_tracker.safe_finish_task(task_id, status="failed", error=str(exc))
        raise

    if bgm_src is not None:
        render_poster.save_ledger(ledger_path, ledger)
    record_used_footage(used_names, cfg)
    task_tracker.safe_finish_task(
        task_id,
        status="done",
        video=str(final_mp4),
        cover_9x16=str(c916),
        cover_3x4=str(c34),
        duration_sec=duration,
        bgm=bgm_label,
    )

    hashtags = " ".join(job.get("hashtags", ["#旧衣回收", "#断舍离", "#亿德海"]))
    (out_dir / "发布文案.md").write_text(
        f"# {title_l1} {title_l2}\n\n{publish_copy or vo_text}\n\n{hashtags}\n\n🔊 音频：{bgm_label}\n⚠️ 提醒：本片含 AI 旁白，发布时请按各平台要求勾选「AI 生成」声明。\n",
        encoding="utf-8",
    )
    meta = {
        "ok": True,
        "mode": args.mode,
        "mode_zh": mode_zh,
        "duration": duration,
        "video": str(final_mp4),
        "cover_9x16": str(c916),
        "cover_3x4": str(c34),
        "qc_contact": str(qc),
        "bgm": bgm_label,
        "used_footage": used_names,
    }
    (out_dir / "发布信息.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
