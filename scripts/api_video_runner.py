#!/usr/bin/env python3
"""
亿德海云端聚合视频 API 防呆调度器（纯标准库，跨平台 macOS / Windows）

核心职责与防重复扣费保障（v2.10.0）：
  1. check  : 调用 GET /v1/models 零扣费校验网关与 Key 连通性，列出当前令牌可用视频模型；
              若配置了 video_api_user_id，额外尝试调用 GET /api/usage/token/ 查询余额。
  2. submit : 先过合规禁用词拦截（命中 0 请求 0 扣费）→ 获取目录级跨进程锁 →
              提交前先原子落盘 api_video_task.json（gen_status="submitting"）并登记 task_tracker →
              调用对应模型 Adapter 发起创建任务 → 拿到 task_id 立即落盘；若超时或网络异常，
              标为 uncertain_timeout 并拦截二次重试。支持 --poll 自动轮询与原子下载校验。
  3. query  : 读取 api_video_task.json 中的 task_id（或显式传入）续查服务端进度，完成后无损下载校验。

内置 5 套协议 Adapter（可通过 --adapter 显式指定或按模型名自动路由）：
  - omni         : OpenAI Videos JSON（如 gemini-omni-1.2-flash）
  - generations  : 统一 Generations JSON（如 sd-2.0 / sd-2.5 / MiniMax-H3）
  - veo_oai      : OpenAI Videos Multipart + /content 下载（如 veo_3_1 / veo_3_1-fast）
  - kling_compat : 可灵兼容协议（如 kling-v3-omni / kling-4.0）
  - wan          : 通义万相协议（如 wan2.7-t2v / wan2.7-i2v / wan3.0-video）
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import media_manager  # noqa: E402
import task_tracker  # noqa: E402

VIDEO_MODEL_HINT_RE = re.compile(
    r"(gemini-omni|omni-\d|veo|sd-\d|seedance|minimax-h\d|hailuo|kling|wan\d.*(?:t2v|i2v|video)|vidu|grok.*video|sora)",
    re.I,
)
SUCCEEDED_STATUSES = {"completed", "succeeded", "success", "succeess", "succeed", "done"}
FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled", "expired"}


def mask_secret(text: str, secret: str) -> str:
    """脱敏输出：绝不在日志、状态文件或报错里回显任何 API Key 明文。"""
    s = str(text or "")
    if secret and len(secret) >= 4:
        s = s.replace(secret, "***")
    return s


def resolve_runtime_settings(args: argparse.Namespace, require_key: bool = True) -> dict[str, str]:
    cfg = media_manager.load_config()
    raw_base = (
        getattr(args, "base_url", "")
        or os.environ.get("YIDEHAI_VIDEO_API_BASE_URL")
        or cfg.get("video_api_base_url")
        or ""
    )
    base_url = media_manager.normalize_video_api_base_url(raw_base)
    api_key = (
        os.environ.get("YIDEHAI_VIDEO_API_KEY")
        or cfg.get("video_api_key")
        or ""
    ).strip()
    user_id = (
        getattr(args, "user_id", "")
        or os.environ.get("YIDEHAI_VIDEO_API_USER_ID")
        or cfg.get("video_api_user_id")
        or ""
    ).strip()
    default_model = (
        os.environ.get("YIDEHAI_VIDEO_API_MODEL")
        or cfg.get("video_api_default_model")
        or "gemini-omni-1.2-flash"
    ).strip()
    if require_key and (not base_url or not api_key):
        raise ValueError(
            "未配置云端视频 API 网关地址或令牌。请先运行：\n"
            "  python3 scripts/media_manager.py config --set-video-api-url \"<BASE_URL>\" --set-video-api-key \"<API_KEY>\""
        )
    return {
        "base_url": base_url,
        "api_key": api_key,
        "user_id": user_id,
        "default_model": default_model,
    }


def resolve_adapter(model: str, explicit: str = "auto") -> str:
    if explicit and explicit != "auto":
        return explicit
    m = (model or "").strip().lower()
    if "omni" in m and "kling" not in m:
        return "omni"
    if m.startswith("sd-") or any(k in m for k in ("doubao", "seedance", "minimax", "hailuo")):
        return "generations"
    if "veo" in m:
        return "veo_oai"
    if "kling" in m:
        return "kling_compat"
    if "wan" in m:
        return "wan"
    raise ValueError(
        f"无法根据模型名 {model!r} 自动识别协议适配器，请显式传入 --adapter omni|generations|veo_oai|kling_compat|wan"
    )


def _auth_headers(api_key: str, user_id: str = "", content_type: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": "yidehai-video/2.10.0",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if user_id:
        headers["New-Api-User"] = user_id
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def http_json(
    method: str,
    url: str,
    api_key: str,
    user_id: str = "",
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[int, dict[str, Any]]:
    data = None
    content_type = ""
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    req = urllib.request.Request(
        url,
        data=data,
        method=method.upper(),
        headers=_auth_headers(api_key, user_id=user_id, content_type=content_type),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                obj = json.loads(raw) if raw.strip() else {}
            except Exception:
                obj = {"raw_text": mask_secret(raw[:1000], api_key)}
            return resp.status, obj if isinstance(obj, dict) else {"data": obj}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            err_obj = json.loads(body)
        except Exception:
            err_obj = {"error": mask_secret(body[:1000], api_key)}
        raise RuntimeError(
            f"HTTP {exc.code} {url}: {mask_secret(json.dumps(err_obj, ensure_ascii=False), api_key)}"
        ) from exc


def encode_multipart_form(
    fields: dict[str, str],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    """纯标准库构建 multipart/form-data 请求体。"""
    boundary = f"----yidehaiBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for k, v in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(v).encode("utf-8"))
        chunks.append(b"\r\n")
    for field_name, filename, raw_bytes, mime_type in files:
        safe_name = filename.replace('"', "_")
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_name}"\r\n'.encode("utf-8")
        )
        chunks.append(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        chunks.append(raw_bytes)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"


def http_multipart(
    url: str,
    api_key: str,
    fields: dict[str, str],
    files: list[tuple[str, str, bytes, str]],
    user_id: str = "",
    timeout: int = 90,
) -> tuple[int, dict[str, Any]]:
    body, content_type = encode_multipart_form(fields, files)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers=_auth_headers(api_key, user_id=user_id, content_type=content_type),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                obj = json.loads(raw) if raw.strip() else {}
            except Exception:
                obj = {"raw_text": mask_secret(raw[:1000], api_key)}
            return resp.status, obj if isinstance(obj, dict) else {"data": obj}
    except urllib.error.HTTPError as exc:
        body_err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} {url}: {mask_secret(body_err[:1000], api_key)}"
        ) from exc


def _image_to_data_uri(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    mime = mime or "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _upload_doubao_file(base_url: str, api_key: str, user_id: str, file_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(file_path))
    mime = mime or "application/octet-stream"
    _, resp = http_multipart(
        f"{base_url}/api/doubao/files/upload",
        api_key=api_key,
        fields={"purpose": "user_data"},
        files=[("file", file_path.name, file_path.read_bytes(), mime)],
        user_id=user_id,
        timeout=90,
    )
    if isinstance(resp.get("url"), str) and resp["url"].startswith(("http://", "https://", "asset://")):
        return resp["url"]
    fid = resp.get("Id") or resp.get("id") or ""
    if not fid:
        raise RuntimeError(f"豆包文件上传未返回有效 Id/url: {resp}")
    status = str(resp.get("Status") or resp.get("status") or "").lower()
    if status == "processing":
        deadline = time.time() + 30
        while time.time() < deadline:
            time.sleep(2)
            try:
                _, q = http_json("GET", f"{base_url}/api/doubao/files/{fid}", api_key=api_key, user_id=user_id, timeout=20)
                st = str(q.get("Status") or q.get("status") or "").lower()
                if st in {"active", "succeeded", "ready"}:
                    break
            except Exception:
                break
    return f"asset://{fid}"


def _resolve_image_reference(
    image_arg: str,
    base_url: str,
    api_key: str,
    user_id: str,
    upload_doubao: bool = False,
) -> str:
    s = (image_arg or "").strip()
    if not s:
        return ""
    if s.startswith(("http://", "https://", "asset://", "data:")):
        return s
    p = Path(s).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"找不到参考图片文件：{p}")
    if upload_doubao:
        return _upload_doubao_file(base_url, api_key, user_id, p)
    return _image_to_data_uri(p)


def extract_task_id(resp: dict[str, Any]) -> str:
    for key in ("task_id", "id", "request_id"):
        v = resp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("task_id", "id", "request_id"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def extract_raw_status(resp: dict[str, Any]) -> str:
    for container in (resp, resp.get("data") if isinstance(resp.get("data"), dict) else {}):
        for key in ("status", "state", "task_status"):
            v = container.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def normalize_status(raw_status: str) -> str:
    low = (raw_status or "").strip().lower()
    if low in SUCCEEDED_STATUSES:
        return "succeeded"
    if low in FAILED_STATUSES:
        return "failed"
    return "running"


def extract_video_url(resp: dict[str, Any]) -> str:
    candidates: list[Any] = [
        resp.get("download_url"),
        resp.get("video_url"),
        resp.get("url"),
    ]
    meta = resp.get("metadata")
    if isinstance(meta, dict):
        candidates.extend([meta.get("url"), meta.get("video_url"), meta.get("download_url")])
    out = resp.get("output")
    if isinstance(out, dict):
        candidates.extend([out.get("video_url"), out.get("url")])
    data = resp.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("download_url"), data.get("video_url"), data.get("url")])
        d_out = data.get("output")
        if isinstance(d_out, dict):
            candidates.extend([d_out.get("video_url"), d_out.get("url")])
        tr = data.get("task_result")
        if isinstance(tr, dict):
            vids = tr.get("videos")
            if isinstance(vids, list) and vids and isinstance(vids[0], dict):
                candidates.append(vids[0].get("url"))
    for c in candidates:
        if isinstance(c, str) and c.strip().startswith(("http://", "https://")):
            return c.strip()
    return ""


def extract_error_message(resp: dict[str, Any], api_key: str = "") -> str:
    for container in (resp, resp.get("data") if isinstance(resp.get("data"), dict) else {}):
        if container.get("fail_reason"):
            return mask_secret(str(container["fail_reason"]), api_key)
        err = container.get("error")
        if isinstance(err, dict) and err.get("message"):
            return mask_secret(str(err["message"]), api_key)
        if isinstance(err, str) and err.strip():
            return mask_secret(err.strip(), api_key)
    if normalize_status(extract_raw_status(resp)) == "failed" and resp.get("message"):
        return mask_secret(str(resp["message"]), api_key)
    return ""


def adapter_submit(
    adapter: str,
    base_url: str,
    api_key: str,
    user_id: str,
    model: str,
    prompt: str,
    duration: int,
    ratio: str,
    resolution: str,
    audio: bool,
    image_arg: str = "",
    upload_doubao: bool = False,
) -> dict[str, Any]:
    if adapter == "omni":
        if 11 <= duration <= 15 and ratio != "9:16":
            raise ValueError("gemini-omni-1.2-flash 11–15 秒仅支持 9:16 竖屏。")
        payload = {
            "model": model,
            "prompt": prompt,
            "seconds": str(int(duration)),
            "resolution": resolution or "720p",
            "aspect_ratio": ratio,
        }
        _, resp = http_json("POST", f"{base_url}/v1/videos", api_key=api_key, user_id=user_id, payload=payload, timeout=90)
        return resp

    if adapter == "generations":
        m_low = model.lower()
        is_minimax = "minimax" in m_low or "hailuo" in m_low
        meta: dict[str, Any] = {
            "ratio": ratio,
            "resolution": resolution or ("768P" if is_minimax else "720p"),
        }
        if is_minimax:
            meta["aigc_watermark"] = False
        else:
            meta["generate_audio"] = bool(audio)
            meta["watermark"] = False
        payload = {
            "model": model,
            "prompt": prompt,
            "duration": int(duration),
            "metadata": meta,
        }
        if image_arg:
            img_ref = _resolve_image_reference(image_arg, base_url, api_key, user_id, upload_doubao=upload_doubao)
            payload["references"] = [{"type": "image_url", "url": img_ref}]
        _, resp = http_json(
            "POST",
            f"{base_url}/v1/video/generations",
            api_key=api_key,
            user_id=user_id,
            payload=payload,
            timeout=90,
        )
        return resp

    if adapter == "veo_oai":
        size = "720x1280" if ratio == "9:16" else ("1280x720" if ratio == "16:9" else ratio)
        fields = {
            "model": model,
            "prompt": prompt,
            "seconds": str(int(duration)),
            "size": size,
            "watermark": "false",
        }
        files: list[tuple[str, str, bytes, str]] = []
        if image_arg:
            p = Path(image_arg).expanduser().resolve()
            if not p.is_file():
                raise FileNotFoundError(f"veo_oai 仅支持传入本地首帧图片路径，未找到：{p}")
            mime, _ = mimetypes.guess_type(str(p))
            files.append(("input_reference", p.name, p.read_bytes(), mime or "image/png"))
        _, resp = http_multipart(
            f"{base_url}/v1/videos",
            api_key=api_key,
            fields=fields,
            files=files,
            user_id=user_id,
            timeout=90,
        )
        return resp

    if adapter == "kling_compat":
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": ratio,
            "duration": int(duration),
            "generate_audio": bool(audio),
        }
        if image_arg:
            img_ref = _resolve_image_reference(image_arg, base_url, api_key, user_id, upload_doubao=False)
            payload["images"] = [{"url": img_ref, "role": "first_frame"}]
        _, resp = http_json(
            "POST",
            f"{base_url}/v1/kling/video/task/create",
            api_key=api_key,
            user_id=user_id,
            payload=payload,
            timeout=90,
        )
        return resp

    if adapter == "wan":
        input_obj: dict[str, Any] = {"prompt": prompt}
        if image_arg:
            img_ref = _resolve_image_reference(image_arg, base_url, api_key, user_id, upload_doubao=False)
            input_obj["media"] = [{"type": "first_frame", "url": img_ref}]
        payload = {
            "model": model,
            "input": input_obj,
            "parameters": {
                "resolution": resolution or "720P",
                "ratio": ratio,
                "duration": int(duration),
                "audio": bool(audio),
                "watermark": False,
            },
        }
        _, resp = http_json(
            "POST",
            f"{base_url}/api/v1/services/aigc/video-generation/video-synthesis",
            api_key=api_key,
            user_id=user_id,
            payload=payload,
            timeout=90,
        )
        return resp

    raise ValueError(f"不支持的 adapter: {adapter}")


def adapter_query(adapter: str, base_url: str, api_key: str, user_id: str, task_id: str) -> dict[str, Any]:
    if adapter == "kling_compat":
        _, resp = http_json(
            "POST",
            f"{base_url}/v1/kling/video/task/status",
            api_key=api_key,
            user_id=user_id,
            payload={"task_id": task_id},
            timeout=45,
        )
        return resp
    if adapter == "wan":
        _, resp = http_json(
            "GET",
            f"{base_url}/api/v1/tasks/{task_id}",
            api_key=api_key,
            user_id=user_id,
            timeout=45,
        )
        return resp
    _, resp = http_json(
        "GET",
        f"{base_url}/v1/videos/{task_id}",
        api_key=api_key,
        user_id=user_id,
        timeout=45,
    )
    return resp


def _probe_video(file_path: Path) -> dict[str, Any]:
    _, ffprobe = media_manager.resolve_ffmpeg_tools()
    if not ffprobe:
        return {}
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_type", "-of", "json", str(file_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        if proc.returncode != 0:
            return {}
        info = json.loads(proc.stdout)
        dur = float((info.get("format") or {}).get("duration") or 0)
        v_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        a_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        return {
            "duration_sec": round(dur, 2) if dur > 0 else None,
            "width": v_stream.get("width"),
            "height": v_stream.get("height"),
            "has_audio": bool(a_stream),
        }
    except Exception:
        return {}


def download_video_file(
    url: str,
    dest_path: Path,
    api_key: str = "",
    user_id: str = "",
    send_auth: bool = False,
) -> dict[str, Any]:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    headers = {"User-Agent": "yidehai-video/2.10.0"}
    if send_auth and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        if user_id:
            headers["New-Api-User"] = user_id
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            with part_path.open("wb") as fh:
                shutil.copyfileobj(resp, fh, length=65536)
        size = part_path.stat().st_size
        head = part_path.read_bytes()[:256].lstrip()
        if size < 10240 or head.startswith((b"{", b"[", b"<!doctype", b"<!DOCTYPE", b"<html", b"<HTML")):
            snippet = head.decode("utf-8", errors="replace")[:180]
            raise RuntimeError(f"下载内容异常（size={size}B），疑似错误页而非 MP4：{mask_secret(snippet, api_key)}")
        os.replace(part_path, dest_path)
    finally:
        if part_path.exists():
            try:
                part_path.unlink()
            except Exception:
                pass
    probe = _probe_video(dest_path)
    return {
        "file": str(dest_path),
        "filename": dest_path.name,
        "bytes": dest_path.stat().st_size,
        **probe,
    }


def _download_from_task_resp(
    adapter: str,
    resp: dict[str, Any],
    task_id: str,
    base_url: str,
    api_key: str,
    user_id: str,
    dest_path: Path,
) -> dict[str, Any]:
    v_url = extract_video_url(resp)
    if v_url:
        return download_video_file(v_url, dest_path, api_key=api_key, user_id=user_id, send_auth=False)
    if adapter == "veo_oai":
        dl_url = f"{base_url}/v1/videos/{task_id}/content"
        return download_video_file(dl_url, dest_path, api_key=api_key, user_id=user_id, send_auth=True)
    raise RuntimeError(f"任务已成功但响应中未找到视频下载地址（task_id={task_id}）")


def _poll_until_done(
    adapter: str,
    base_url: str,
    api_key: str,
    user_id: str,
    task_id: str,
    poll_seconds: int,
    poll_interval: int,
    state_file: Path | None = None,
    record: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    deadline = time.time() + max(0, poll_seconds)
    last_resp: dict[str, Any] = {}
    while True:
        last_resp = adapter_query(adapter, base_url, api_key, user_id, task_id)
        raw_status = extract_raw_status(last_resp) or "running"
        norm_status = normalize_status(raw_status)
        if record is not None and state_file is not None:
            record["raw_status"] = raw_status
            record["gen_status"] = norm_status
            record["last_query_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if last_resp.get("progress") is not None:
                record["progress"] = last_resp.get("progress")
            media_manager.atomic_write_json(state_file, record)
        if norm_status in {"succeeded", "failed"}:
            return norm_status, raw_status, last_resp
        if time.time() >= deadline:
            return "running", raw_status, last_resp
        time.sleep(max(1, min(poll_interval, int(max(1, deadline - time.time())))))


def cmd_check(args: argparse.Namespace) -> None:
    settings = resolve_runtime_settings(args, require_key=True)
    base_url = settings["base_url"]
    api_key = settings["api_key"]
    user_id = settings["user_id"]

    _, models_resp = http_json("GET", f"{base_url}/v1/models", api_key=api_key, user_id=user_id, timeout=30)
    raw_items = models_resp.get("data") if isinstance(models_resp.get("data"), list) else []
    all_ids = [str(item.get("id")) for item in raw_items if isinstance(item, dict) and item.get("id")]
    video_models = [mid for mid in all_ids if VIDEO_MODEL_HINT_RE.search(mid)]

    usage_info: dict[str, Any] | None = None
    usage_note = ""
    if user_id:
        try:
            _, u_resp = http_json("GET", f"{base_url}/api/usage/token/", api_key=api_key, user_id=user_id, timeout=20)
            usage_info = u_resp
        except Exception as exc:
            usage_note = mask_secret(str(exc), api_key)
    else:
        usage_note = "未配置 video_api_user_id，跳过 /api/usage/token/ 额度查询（仅执行零扣费 /v1/models 校验）。"

    print(json.dumps({
        "ok": True,
        "base_url": base_url,
        "default_model": settings["default_model"],
        "total_models": len(all_ids),
        "video_models": video_models,
        "usage": usage_info,
        "usage_note": usage_note,
    }, ensure_ascii=False, indent=2))


def cmd_submit(args: argparse.Namespace) -> None:
    # 1. 硬拦截合规禁用词（0 请求、0 扣费）
    hits = media_manager.check_forbidden_terms([args.prompt])
    if hits:
        print(json.dumps({
            "ok": False,
            "blocked": "COMPLIANCE_FORBIDDEN_TERMS",
            "hits": hits,
            "message": f"提示词/台词触发合规红线禁用词 {hits}，已拦截提交（0 扣费）。",
        }, ensure_ascii=False, indent=2))
        sys.exit(2)

    settings = resolve_runtime_settings(args, require_key=True)
    base_url = settings["base_url"]
    api_key = settings["api_key"]
    user_id = settings["user_id"]
    model = (args.model or settings["default_model"]).strip()
    adapter = resolve_adapter(model, args.adapter)

    task_dir = Path(args.task_dir).expanduser().resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    state_file = task_dir / "api_video_task.json"
    lock_file = task_dir / ".api_video.lock"
    slug = media_manager.sanitize_slug(args.slug or model, fallback="api-video")
    raw_mp4 = task_dir / f"{slug}_raw.mp4"

    with media_manager.file_lock(lock_file, timeout=15.0, stale_seconds=max(3600.0, float(args.poll or 0) + 300.0)):
        prev: dict[str, Any] | None = None
        if state_file.exists():
            try:
                prev = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                prev = {"gen_status": "corrupted_state"}

        if prev is not None and not args.force_new:
            prev_id = prev.get("task_id")
            prev_status = prev.get("gen_status")
            print(json.dumps({
                "ok": False,
                "blocked": "EXISTING_TASK_STATE",
                "message": (
                    f"该任务目录已存在历史提交记录（status={prev_status}, task_id={prev_id or '待核实'}）。"
                    "为防止重复扣费已拦截新提交：请先运行 `query --task-dir ... --download` 核实服务端状态；"
                    "仅在确认失败未扣费或已获新预算授权后，才可加 --force-new 重提。"
                ),
                "state_file": state_file.name,
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

        client_task_id = f"av-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        attempts = list(prev.get("attempts", [])) if isinstance(prev, dict) else []
        if isinstance(prev, dict) and prev.get("client_task_id"):
            attempts.append({
                "client_task_id": prev.get("client_task_id"),
                "task_id": prev.get("task_id"),
                "gen_status": prev.get("gen_status"),
                "submitted_at": prev.get("submitted_at"),
            })

        # 提交前先原子落盘待确认状态 + 写入跨 Agent 任务台账
        record: dict[str, Any] = {
            "client_task_id": client_task_id,
            "base_url": base_url,
            "model": model,
            "adapter": adapter,
            "duration": args.duration,
            "ratio": args.ratio,
            "resolution": args.resolution,
            "audio": bool(args.audio),
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "task_id": None,
            "raw_status": None,
            "gen_status": "submitting",
            "fail_reason": None,
            "downloaded_file": None,
            "attempts": attempts,
        }
        media_manager.atomic_write_json(state_file, record)

        tracker_id = task_tracker.safe_start_task(
            track="api_video",
            title=args.title or slug,
            slug=slug,
            out_dir=str(task_dir),
            note=f"model={model} adapter={adapter}",
        )
        record["tracker_task_id"] = tracker_id
        media_manager.atomic_write_json(state_file, record)

        try:
            resp = adapter_submit(
                adapter=adapter,
                base_url=base_url,
                api_key=api_key,
                user_id=user_id,
                model=model,
                prompt=args.prompt,
                duration=args.duration,
                ratio=args.ratio,
                resolution=args.resolution,
                audio=bool(args.audio),
                image_arg=args.image,
                upload_doubao=bool(args.upload_doubao),
            )
        except Exception as exc:
            err_msg = mask_secret(str(exc), api_key)
            is_http_err = err_msg.startswith("HTTP ")
            record["gen_status"] = "submit_failed" if is_http_err else "uncertain_timeout"
            record["fail_reason"] = err_msg
            media_manager.atomic_write_json(state_file, record)
            task_tracker.safe_finish_task(
                tracker_id,
                status="failed" if is_http_err else "interrupted",
                error=err_msg,
            )
            print(json.dumps({
                "ok": False,
                "client_task_id": client_task_id,
                "gen_status": record["gen_status"],
                "message": err_msg,
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

        task_id = extract_task_id(resp)
        raw_status = extract_raw_status(resp) or "submitted"
        if not task_id:
            err_msg = "接口返回成功但未解析到 task_id/id，已标为 uncertain_no_id 禁止盲目重试。"
            record["gen_status"] = "uncertain_no_id"
            record["fail_reason"] = err_msg
            media_manager.atomic_write_json(state_file, record)
            task_tracker.safe_finish_task(tracker_id, status="interrupted", error=err_msg)
            print(json.dumps({
                "ok": False,
                "client_task_id": client_task_id,
                "gen_status": "uncertain_no_id",
                "message": err_msg,
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

        record["task_id"] = task_id
        record["raw_status"] = raw_status
        record["gen_status"] = "submitted"
        media_manager.atomic_write_json(state_file, record)

        if args.poll <= 0:
            task_tracker.safe_finish_task(
                tracker_id,
                status="pending_render",
                note=f"model={model} task_id={task_id} 已提交云端，待 query 下载",
            )
            print(json.dumps({
                "ok": True,
                "client_task_id": client_task_id,
                "task_id": task_id,
                "adapter": adapter,
                "model": model,
                "gen_status": "submitted",
                "raw_status": raw_status,
            }, ensure_ascii=False, indent=2))
            return

        # 进入轮询并自动下载
        norm_status, raw_status, last_resp = _poll_until_done(
            adapter=adapter,
            base_url=base_url,
            api_key=api_key,
            user_id=user_id,
            task_id=task_id,
            poll_seconds=args.poll,
            poll_interval=args.poll_interval,
            state_file=state_file,
            record=record,
        )

        if norm_status == "succeeded":
            dl_info = _download_from_task_resp(
                adapter=adapter,
                resp=last_resp,
                task_id=task_id,
                base_url=base_url,
                api_key=api_key,
                user_id=user_id,
                dest_path=raw_mp4,
            )
            record["gen_status"] = "done"
            record["raw_status"] = raw_status
            record["downloaded_file"] = dl_info["file"]
            media_manager.atomic_write_json(state_file, record)
            task_tracker.safe_finish_task(
                tracker_id,
                status="done",
                video=dl_info["file"],
                duration_sec=dl_info.get("duration_sec"),
                note=f"model={model} task_id={task_id}",
            )
            print(json.dumps({
                "ok": True,
                "client_task_id": client_task_id,
                "task_id": task_id,
                "adapter": adapter,
                "model": model,
                "gen_status": "done",
                "raw_status": raw_status,
                "download": dl_info,
            }, ensure_ascii=False, indent=2))
            return

        if norm_status == "failed":
            err_msg = extract_error_message(last_resp, api_key=api_key) or f"云端生成失败（status={raw_status}）"
            record["gen_status"] = "failed"
            record["fail_reason"] = err_msg
            media_manager.atomic_write_json(state_file, record)
            task_tracker.safe_finish_task(tracker_id, status="failed", error=err_msg)
            print(json.dumps({
                "ok": False,
                "client_task_id": client_task_id,
                "task_id": task_id,
                "gen_status": "failed",
                "raw_status": raw_status,
                "message": err_msg,
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

        # 轮询到期仍排队/生成中，标 pending_render 方便续查
        record["gen_status"] = "running"
        media_manager.atomic_write_json(state_file, record)
        task_tracker.safe_finish_task(
            tracker_id,
            status="pending_render",
            note=f"model={model} task_id={task_id} 轮询到期仍为 {raw_status}，请执行 query --download",
        )
        print(json.dumps({
            "ok": True,
            "completed": False,
            "client_task_id": client_task_id,
            "task_id": task_id,
            "gen_status": "running",
            "raw_status": raw_status,
            "action_required": "任务仍在云端处理中，请稍后运行 query --task-dir ... --download 续查并下载，切勿重新 submit。",
        }, ensure_ascii=False, indent=2))


def cmd_query(args: argparse.Namespace) -> None:
    settings = resolve_runtime_settings(args, require_key=True)
    base_url = settings["base_url"]
    api_key = settings["api_key"]
    user_id = settings["user_id"]

    task_dir = Path(args.task_dir).expanduser().resolve()
    state_file = task_dir / "api_video_task.json"
    state: dict[str, Any] = {}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))

    saved_id = state.get("task_id")
    saved_client_id = state.get("client_task_id")
    if args.task_id and saved_id and args.task_id != saved_id:
        raise ValueError(
            f"显式传入的 --task-id ({args.task_id}) 与目录内保存的 task_id ({saved_id}) 不一致，已拒绝覆盖原状态文件。"
        )
    task_id = (args.task_id or saved_id or "").strip()
    if not task_id:
        raise ValueError(f"未提供 --task-id，且 {state_file.name} 中无 task_id。")

    adapter = args.adapter
    if adapter == "auto":
        adapter = state.get("adapter") or resolve_adapter(args.model or state.get("model") or settings["default_model"], "auto")

    if args.poll > 0:
        norm_status, raw_status, resp = _poll_until_done(
            adapter=adapter,
            base_url=base_url,
            api_key=api_key,
            user_id=user_id,
            task_id=task_id,
            poll_seconds=args.poll,
            poll_interval=args.poll_interval,
        )
    else:
        resp = adapter_query(adapter, base_url, api_key, user_id, task_id)
        raw_status = extract_raw_status(resp) or "running"
        norm_status = normalize_status(raw_status)

    dl_info: dict[str, Any] | None = None
    if norm_status == "succeeded" and args.download:
        slug = media_manager.sanitize_slug(state.get("model") or "api-video", fallback="api-video")
        dest_path = task_dir / f"{slug}_raw.mp4"
        dl_info = _download_from_task_resp(adapter, resp, task_id, base_url, api_key, user_id, dest_path)

    if state_file.exists():
        with media_manager.file_lock(task_dir / ".api_video.lock", timeout=15.0):
            latest = json.loads(state_file.read_text(encoding="utf-8"))
            if saved_client_id and latest.get("client_task_id") and latest.get("client_task_id") != saved_client_id:
                raise ValueError("状态文件已被新提交更新，已拒绝覆盖。")
            latest["task_id"] = task_id
            latest["raw_status"] = raw_status
            latest["gen_status"] = "done" if dl_info else norm_status
            latest["last_query_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if dl_info:
                latest["downloaded_file"] = dl_info["file"]
            err_msg = extract_error_message(resp, api_key=api_key)
            if err_msg:
                latest["fail_reason"] = err_msg
            media_manager.atomic_write_json(state_file, latest)

            tid = latest.get("tracker_task_id") or ""
            if tid:
                if dl_info:
                    task_tracker.safe_finish_task(tid, status="done", video=dl_info["file"], duration_sec=dl_info.get("duration_sec"))
                elif norm_status == "failed":
                    task_tracker.safe_finish_task(tid, status="failed", error=err_msg or f"status={raw_status}")

    print(json.dumps({
        "ok": norm_status != "failed",
        "task_id": task_id,
        "adapter": adapter,
        "gen_status": "done" if dl_info else norm_status,
        "raw_status": raw_status,
        "video_url": extract_video_url(resp),
        "download": dl_info,
        "fail_reason": extract_error_message(resp, api_key=api_key),
    }, ensure_ascii=False, indent=2))
    if norm_status == "failed":
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海云端聚合视频 API 防呆调度器（v2.10.0）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_chk = sub.add_parser("check", help="零扣费校验网关与 Key 连通性，列出可用视频模型")
    p_chk.add_argument("--base-url", default="", help="可选覆盖网关基址（如 https://api.tiantoken.com）")
    p_chk.add_argument("--user-id", default="", help="可选 New-Api-User ID（用于查询令牌额度）")

    p_sub = sub.add_parser("submit", help="防重提交视频生成任务并预先原子落盘")
    p_sub.add_argument("--task-dir", required=True, help="任务目录（保存 api_video_task.json 与下载原片）")
    p_sub.add_argument("--prompt", required=True, help="生成提示词（提交前自动过合规词检查）")
    p_sub.add_argument("--model", default="", help="模型名（默认读取配置 video_api_default_model 或 gemini-omni-1.2-flash）")
    p_sub.add_argument("--adapter", choices=["auto", "omni", "generations", "veo_oai", "kling_compat", "wan"], default="auto")
    p_sub.add_argument("--duration", type=int, default=8, help="视频时长（秒，默认 8）")
    p_sub.add_argument("--ratio", default="9:16", help="画面比例（默认 9:16 竖屏）")
    p_sub.add_argument("--resolution", default="", help="可选分辨率（如 720p / 768P）")
    p_sub.add_argument("--audio", dest="audio", action="store_true", default=True, help="开启原生声音（默认开启）")
    p_sub.add_argument("--no-audio", dest="audio", action="store_false", help="关闭原生声音（无声开场镜头用）")
    p_sub.add_argument("--image", default="", help="可选首帧/参考图片（本地路径或公网 URL）")
    p_sub.add_argument("--upload-doubao", action="store_true", help="豆包图生视频时先上传到 /api/doubao/files/upload 获取 asset://")
    p_sub.add_argument("--slug", default="", help="可选输出短标识与台账标题前缀")
    p_sub.add_argument("--title", default="", help="可选任务台账标题")
    p_sub.add_argument("--poll", type=int, default=300, help="提交后最多轮询秒数并自动下载（0 表示只提交不等）")
    p_sub.add_argument("--poll-interval", type=int, default=5, help="轮询间隔秒数（默认 5s）")
    p_sub.add_argument("--force-new", action="store_true", help="确认未扣费或获新预算授权后归档旧尝试并新提交")
    p_sub.add_argument("--base-url", default="", help="可选覆盖网关基址")
    p_sub.add_argument("--user-id", default="", help="可选 New-Api-User ID")

    p_q = sub.add_parser("query", help="按已保存的 task_id 续查进度并下载")
    p_q.add_argument("--task-dir", required=True, help="任务目录")
    p_q.add_argument("--task-id", default="", help="可选显式 task_id")
    p_q.add_argument("--model", default="", help="可选模型名（仅未读到状态文件时用于识别协议）")
    p_q.add_argument("--adapter", choices=["auto", "omni", "generations", "veo_oai", "kling_compat", "wan"], default="auto")
    p_q.add_argument("--poll", type=int, default=0, help="可选轮询秒数（默认 0 仅查一次）")
    p_q.add_argument("--poll-interval", type=int, default=5, help="轮询间隔秒数")
    p_q.add_argument("--download", action="store_true", help="完成后下载 MP4 原片到任务目录")
    p_q.add_argument("--base-url", default="", help="可选覆盖网关基址")
    p_q.add_argument("--user-id", default="", help="可选 New-Api-User ID")

    args = parser.parse_args()
    if args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "submit":
        cmd_submit(args)
    elif args.cmd == "query":
        cmd_query(args)


if __name__ == "__main__":
    main()
