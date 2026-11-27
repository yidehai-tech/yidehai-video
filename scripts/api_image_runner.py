#!/usr/bin/env python3
"""
亿德海「图文故事片」云端聚合生图调度器（v2.11.0 · 纯标准库 + Pillow）

直接复用本机已配置的 video_api_base_url 与 video_api_key（同一把网关令牌，零额外配置），
避免高单价视频试错消耗，将成本降到 AI 视频的约 1/10（图文故事片一鱼两吃主力）。

内置 3 套生图协议 Adapter（按模型名自动路由或 --adapter 显式指定）：
  - gemini_img : POST /v1beta/models/{model}:generateContent（如 gemini-3.1-flash-lite-image / gemini-2.5-flash-image）
  - doubao_img : POST /api/v3/images/generations（如 doubao-seedream-5-5 / doubao-seedream-5-0-pro-260628）
  - openai_img : POST /v1/images/generations（如 gpt-image-2 / gpt-image-2.6-flare / flux）
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import api_video_runner  # noqa: E402
import media_manager  # noqa: E402

IMAGE_MODEL_HINT_RE = re.compile(
    r"(image|seedream|flux|banana|imagen|dall-e|midjourney|mj-)",
    re.I,
)
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-lite-image"


def resolve_image_settings(base_url: str = "", user_id: str = "") -> dict[str, str]:
    cfg = media_manager.load_config()
    raw_base = (
        base_url
        or os.environ.get("YIDEHAI_VIDEO_API_BASE_URL")
        or cfg.get("video_api_base_url")
        or ""
    )
    norm_base = media_manager.normalize_video_api_base_url(raw_base)
    api_key = (
        os.environ.get("YIDEHAI_VIDEO_API_KEY")
        or cfg.get("video_api_key")
        or ""
    ).strip()
    uid = (
        user_id
        or os.environ.get("YIDEHAI_VIDEO_API_USER_ID")
        or cfg.get("video_api_user_id")
        or ""
    ).strip()
    default_model = (
        os.environ.get("YIDEHAI_IMAGE_API_MODEL")
        or cfg.get("image_api_default_model")
        or DEFAULT_IMAGE_MODEL
    ).strip()
    if not norm_base or not api_key:
        raise ValueError(
            "未配置云端 API 网关地址或令牌。请先运行：\n"
            "  python3 scripts/media_manager.py config --set-video-api-url \"<BASE_URL>\" --set-video-api-key \"<API_KEY>\""
        )
    return {
        "base_url": norm_base,
        "api_key": api_key,
        "user_id": uid,
        "default_model": default_model,
    }


def resolve_image_adapter(model: str, explicit: str = "auto") -> str:
    if explicit and explicit != "auto":
        return explicit
    m = (model or "").strip().lower()
    if any(k in m for k in ("gemini", "banana", "imagen")):
        return "gemini_img"
    if any(k in m for k in ("seedream", "doubao")):
        return "doubao_img"
    if any(k in m for k in ("gpt-image", "flux", "grok", "dall")):
        return "openai_img"
    raise ValueError(
        f"无法根据模型名 {model!r} 自动识别生图协议，请显式传入 --adapter gemini_img|doubao_img|openai_img"
    )


def _valid_image_magic(raw: bytes) -> bool:
    if len(raw) < 2048:
        return False
    if raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff"):
        return True
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return True
    return False


def _save_validated_image(raw_bytes: bytes, dest_path: Path) -> dict[str, Any]:
    if not _valid_image_magic(raw_bytes):
        head_txt = raw_bytes[:160].decode("utf-8", errors="replace")
        raise RuntimeError(f"生成结果不是有效的 PNG/JPEG/WebP 图片（bytes={len(raw_bytes)}）：{head_txt}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    try:
        part_path.write_bytes(raw_bytes)
        os.replace(part_path, dest_path)
    finally:
        if part_path.exists():
            try:
                part_path.unlink()
            except Exception:
                pass

    info: dict[str, Any] = {
        "file": str(dest_path),
        "bytes": dest_path.stat().st_size,
    }
    try:
        from PIL import Image  # type: ignore

        with Image.open(dest_path) as im:
            info["width"] = im.width
            info["height"] = im.height
            info["format"] = im.format
    except Exception:
        pass
    return info


def _download_bytes(url: str, api_key: str = "") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "yidehai-video/2.11.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except Exception as exc:
        raise RuntimeError(f"下载生图结果失败: {api_video_runner.mask_secret(str(exc), api_key)}") from exc


def _extract_image_bytes(resp: dict[str, Any], api_key: str = "") -> bytes:
    # 1) Gemini generateContent: candidates[].content.parts[].inlineData / inline_data
    for cand in resp.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        parts = (cand.get("content") or {}).get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                return base64.b64decode(str(inline["data"]))
            txt = part.get("text")
            if isinstance(txt, str) and txt:
                m_b64 = re.search(r"data:image/[a-zA-Z0-9+.-]+;base64,([A-Za-z0-9+/=]+)", txt)
                if m_b64:
                    return base64.b64decode(m_b64.group(1))
                m_url = re.search(r"https?://[^\s)\"'>]+", txt)
                if m_url:
                    return _download_bytes(m_url.group(0), api_key=api_key)

    # 2) OpenAI / Doubao / Flux standard data: [{b64_json | url}]
    data_list = resp.get("data")
    if isinstance(data_list, list):
        for item in data_list:
            if not isinstance(item, dict):
                continue
            if item.get("b64_json"):
                return base64.b64decode(str(item["b64_json"]))
            if isinstance(item.get("url"), str) and item["url"].startswith(("http://", "https://")):
                return _download_bytes(item["url"], api_key=api_key)

    # 3) Chat-style fallback (choices[].message.content)
    for choice in resp.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            m_b64 = re.search(r"data:image/[a-zA-Z0-9+.-]+;base64,([A-Za-z0-9+/=]+)", content)
            if m_b64:
                return base64.b64decode(m_b64.group(1))
            m_url = re.search(r"https?://[^\s)\"'>]+", content)
            if m_url:
                return _download_bytes(m_url.group(0), api_key=api_key)

    raise RuntimeError(
        f"响应中未解析到图片数据（b64_json/inlineData/url）：{api_video_runner.mask_secret(json.dumps(resp, ensure_ascii=False)[:400], api_key)}"
    )


def generate_one(
    prompt: str,
    out_path: str | Path,
    model: str = "",
    ratio: str = "9:16",
    size: str = "",
    adapter: str = "auto",
    force: bool = False,
    base_url: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    """生成单张合规分镜图并原子校验落盘；目标已存在且未传 force 时直接跳过（0 扣费）。"""
    hits = media_manager.check_forbidden_terms([prompt])
    if hits:
        raise ValueError(f"生图提示词命中合规禁用词 {hits}，已拦截（0 扣费）。")

    dest = Path(out_path).expanduser().resolve()
    if dest.is_file() and dest.stat().st_size > 2048 and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "目标图片已存在，已跳过重复生成（0 扣费）；如需重出请加 --force。",
            "file": str(dest),
            "bytes": dest.stat().st_size,
        }

    settings = resolve_image_settings(base_url=base_url, user_id=user_id)
    chosen_model = (model or settings["default_model"]).strip()
    chosen_adapter = resolve_image_adapter(chosen_model, explicit=adapter)
    url_base = settings["base_url"]
    api_key = settings["api_key"]
    uid = settings["user_id"]

    if chosen_adapter == "gemini_img":
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": ratio},
            },
        }
        _, resp = api_video_runner.http_json(
            "POST",
            f"{url_base}/v1beta/models/{chosen_model}:generateContent",
            api_key=api_key,
            user_id=uid,
            payload=payload,
            timeout=120,
        )
    elif chosen_adapter == "doubao_img":
        size_val = size.strip() or {
            "9:16": "1440x2560",
            "3:4": "1440x1920",
            "1:1": "2048x2048",
            "16:9": "2560x1440",
        }.get(ratio, "1440x2560")
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "size": size_val,
            "watermark": False,
            "response_format": "url",
        }
        _, resp = api_video_runner.http_json(
            "POST",
            f"{url_base}/api/v3/images/generations",
            api_key=api_key,
            user_id=uid,
            payload=payload,
            timeout=120,
        )
    elif chosen_adapter == "openai_img":
        size_val = size.strip() or {
            "9:16": "1024x1536",
            "3:4": "1024x1536",
            "1:1": "1024x1024",
            "16:9": "1536x1024",
        }.get(ratio, "1024x1536")
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "n": 1,
            "size": size_val,
        }
        _, resp = api_video_runner.http_json(
            "POST",
            f"{url_base}/v1/images/generations",
            api_key=api_key,
            user_id=uid,
            payload=payload,
            timeout=120,
        )
    else:
        raise ValueError(f"不支持的生图 adapter: {chosen_adapter}")

    raw_bytes = _extract_image_bytes(resp, api_key=api_key)
    saved = _save_validated_image(raw_bytes, dest)
    return {
        "ok": True,
        "skipped": False,
        "model": chosen_model,
        "adapter": chosen_adapter,
        "ratio": ratio,
        **saved,
    }


def cmd_check(args: argparse.Namespace) -> None:
    settings = resolve_image_settings(base_url=args.base_url, user_id=args.user_id)
    _, models_resp = api_video_runner.http_json(
        "GET",
        f"{settings['base_url']}/v1/models",
        api_key=settings["api_key"],
        user_id=settings["user_id"],
        timeout=30,
    )
    raw_items = models_resp.get("data") if isinstance(models_resp.get("data"), list) else []
    all_ids = [str(x.get("id")) for x in raw_items if isinstance(x, dict) and x.get("id")]
    image_models = sorted(mid for mid in all_ids if IMAGE_MODEL_HINT_RE.search(mid))
    print(json.dumps({
        "ok": True,
        "base_url": settings["base_url"],
        "default_model": settings["default_model"],
        "total_models": len(all_ids),
        "image_models": image_models,
    }, ensure_ascii=False, indent=2))


def cmd_generate(args: argparse.Namespace) -> None:
    res = generate_one(
        prompt=args.prompt,
        out_path=args.out,
        model=args.model,
        ratio=args.ratio,
        size=args.size,
        adapter=args.adapter,
        force=args.force,
        base_url=args.base_url,
        user_id=args.user_id,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_batch(args: argparse.Namespace) -> None:
    spec_path = Path(args.manifest).expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    items = spec.get("items") or []
    if not items:
        raise ValueError("manifest 必须包含非空的 items 列表。")
    model = args.model or str(spec.get("model") or "")
    ratio = str(spec.get("ratio") or args.ratio or "9:16")
    size = str(spec.get("size") or "")
    prefix = str(spec.get("style_prefix") or "").strip()
    suffix = str(spec.get("no_text_suffix") or "").strip()

    results = []
    for idx, item in enumerate(items, 1):
        raw_p = str(item.get("prompt") or "").strip()
        if not raw_p:
            raise ValueError(f"第 {idx} 条 item 缺少 prompt。")
        parts = [p for p in (prefix, raw_p, suffix) if p]
        full_prompt = " ".join(parts)
        out_p = Path(item["out"]) if item.get("out") else (spec_path.parent / f"{idx:02d}.png")
        res = generate_one(
            prompt=full_prompt,
            out_path=out_p,
            model=str(item.get("model") or model),
            ratio=str(item.get("ratio") or ratio),
            size=str(item.get("size") or size),
            adapter=args.adapter,
            force=args.force,
            base_url=args.base_url,
            user_id=args.user_id,
        )
        results.append(res)
    print(json.dumps({"ok": True, "count": len(results), "items": results}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海云端聚合生图调度器（v2.11.0 · 复用已有 API Key）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_chk = sub.add_parser("check", help="零扣费校验当前令牌可见的生图模型列表")
    p_chk.add_argument("--base-url", default="", help="可选覆盖网关基址")
    p_chk.add_argument("--user-id", default="", help="可选 New-Api-User ID")

    p_gen = sub.add_parser("generate", help="生成单张分镜图（已存在则自动跳过防重复扣费）")
    p_gen.add_argument("--prompt", required=True, help="生图提示词")
    p_gen.add_argument("--out", required=True, help="输出图片路径（建议 .png / .jpg）")
    p_gen.add_argument("--model", default="", help="模型名（默认读取 image_api_default_model 或 gemini-3.1-flash-lite-image）")
    p_gen.add_argument("--ratio", default="9:16", help="宽高比（默认 9:16 竖屏）")
    p_gen.add_argument("--size", default="", help="可选精确尺寸（仅 doubao_img / openai_img 使用）")
    p_gen.add_argument("--adapter", choices=["auto", "gemini_img", "doubao_img", "openai_img"], default="auto")
    p_gen.add_argument("--force", action="store_true", help="即使目标图片已存在也强制重新生成")
    p_gen.add_argument("--base-url", default="", help="可选覆盖网关基址")
    p_gen.add_argument("--user-id", default="", help="可选 New-Api-User ID")

    p_bat = sub.add_parser("batch", help="按 JSON 清单批量生成分镜图（支持断点续跑跳过已生成项）")
    p_bat.add_argument("--manifest", required=True, help="生图清单 JSON 路径")
    p_bat.add_argument("--model", default="", help="可选覆盖清单内默认模型")
    p_bat.add_argument("--ratio", default="9:16", help="默认宽高比")
    p_bat.add_argument("--adapter", choices=["auto", "gemini_img", "doubao_img", "openai_img"], default="auto")
    p_bat.add_argument("--force", action="store_true", help="强制覆盖已有图片")
    p_bat.add_argument("--base-url", default="", help="可选覆盖网关基址")
    p_bat.add_argument("--user-id", default="", help="可选 New-Api-User ID")

    args = parser.parse_args()
    if args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "batch":
        cmd_batch(args)


if __name__ == "__main__":
    main()
