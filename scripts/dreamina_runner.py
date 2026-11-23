#!/usr/bin/env python3
"""
即梦（Dreamina）官方 CLI 防呆调度器（跨平台 macOS / Windows，纯标准库）

核心职责：
  1. check  : 检查本机是否安装 dreamina CLI 并查询账号积分余额（user_credit）
  2. submit : 提交视频生成任务（text2video / image2video / frames2video / multimodal2video），
              并把 submit_id 落盘到 <task-dir>/dreamina_task.json；若同目录已存在未完成的 submit_id，
              默认拒绝重复提交，防止误扣双倍积分！
  3. query  : 按 dreamina_task.json 中的 submit_id 查询进度；gen_status=success 时通过 --download_dir
              无损下载成片原素材到任务目录。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def resolve_dreamina() -> str:
    exe = shutil.which("dreamina") or shutil.which("dreamina.exe")
    if exe:
        return exe
    for cand in [
        Path.home() / ".local" / "bin" / "dreamina",
        Path.home() / ".local" / "bin" / "dreamina.exe",
    ]:
        if cand.is_file():
            return str(cand)
    raise FileNotFoundError(
        "未找到 dreamina CLI。请先安装即梦官方 CLI 并执行 `dreamina login` 完成扫码登录。"
    )


def run_cli(cmd: list[str], timeout: int = 180) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_json_or_fields(text: str) -> dict[str, Any]:
    text_s = text.strip()
    # Try direct JSON or last JSON object in output
    try:
        obj = json.loads(text_s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    matches = list(re.finditer(r"\{[\s\S]*?\}", text_s))
    for m in reversed(matches):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    out: dict[str, Any] = {}
    for key in ("submit_id", "gen_status", "fail_reason", "estimated_remaining_seconds"):
        m = re.search(rf"{key}\s*[:=]\s*[\"']?([^\s,\"'}}]+)", text_s)
        if m:
            out[key] = m.group(1)
    return out


def cmd_check() -> None:
    exe = resolve_dreamina()
    rc_v, out_v, err_v = run_cli([exe, "--version"], timeout=20)
    rc_c, out_c, err_c = run_cli([exe, "user_credit"], timeout=30)
    print(json.dumps({
        "ok": rc_c == 0,
        "dreamina_bin": exe,
        "version": (out_v or err_v).strip(),
        "credit_raw": (out_c or err_c).strip(),
        "credit_parsed": parse_json_or_fields(out_c),
    }, ensure_ascii=False, indent=2))
    if rc_c != 0:
        sys.exit(1)


def cmd_submit(args: argparse.Namespace) -> None:
    exe = resolve_dreamina()
    task_dir = Path(args.task_dir).expanduser().resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    state_file = task_dir / "dreamina_task.json"

    if state_file.exists() and not args.force_new:
        prev = json.loads(state_file.read_text(encoding="utf-8"))
        prev_id = prev.get("submit_id")
        prev_status = prev.get("gen_status")
        if prev_id and prev_status not in ("fail",):
            print(json.dumps({
                "ok": False,
                "blocked": "EXISTING_SUBMIT_ID",
                "message": (
                    f"该任务目录已存在 submit_id={prev_id}（状态：{prev_status}），"
                    "为防止重复扣积分已拦截新提交。请先运行 `query` 续查，或确认废弃后加 --force-new。"
                ),
                "state_file": str(state_file),
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

    cmd = [exe, args.mode, f"--prompt={args.prompt}"]
    if args.duration:
        cmd.append(f"--duration={args.duration}")
    if args.ratio:
        cmd.append(f"--ratio={args.ratio}")
    if args.video_resolution:
        cmd.append(f"--video_resolution={args.video_resolution}")
    if args.model_version:
        cmd.append(f"--model_version={args.model_version}")
    if args.image:
        cmd.append(f"--image={str(Path(args.image).expanduser().resolve())}")
    if args.poll and args.poll > 0:
        cmd.append(f"--poll={args.poll}")
    if args.extra:
        cmd.extend(args.extra)

    rc, stdout, stderr = run_cli(cmd, timeout=max(120, (args.poll or 0) + 60))
    parsed = parse_json_or_fields(stdout + "\n" + stderr)
    submit_id = parsed.get("submit_id")
    gen_status = parsed.get("gen_status") or ("submitted" if rc == 0 else "error")

    record = {
        "mode": args.mode,
        "command": cmd,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "submit_id": submit_id,
        "gen_status": gen_status,
        "fail_reason": parsed.get("fail_reason"),
        "estimated_remaining_seconds": parsed.get("estimated_remaining_seconds"),
        "returncode": rc,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    state_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    result: dict[str, Any] = {
        "ok": rc == 0 and bool(submit_id),
        "submit_id": submit_id,
        "gen_status": gen_status,
        "state_file": str(state_file),
        "parsed": parsed,
    }
    if "AigcComplianceConfirmationRequired" in (stdout + stderr):
        result["action_required"] = "该模型首次使用需先在即梦 Web 端完成一次合规确认生成，确认后再重试。"
    elif "ExceedConcurrencyLimit" in (stdout + stderr) or "1310" in (stdout + stderr):
        result["action_required"] = "触发即梦并发限制，请勿重复提交，先用 list_task / query 检查排队任务或切换对应 VIP 变体。"

    # 若 poll 期间已直接成功，顺手通过 --download_dir 下载原片
    if gen_status == "success" and submit_id and args.auto_download:
        dl_info = _download_result(exe, submit_id, task_dir)
        result["download"] = dl_info

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        sys.exit(1)


def _download_result(exe: str, submit_id: str, download_dir: Path) -> dict[str, Any]:
    download_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in download_dir.glob("*") if p.is_file()}
    rc, stdout, stderr = run_cli(
        [exe, "query_result", f"--submit_id={submit_id}", f"--download_dir={download_dir}"],
        timeout=240,
    )
    after = [p for p in download_dir.glob("*") if p.is_file() and p.name not in before]
    parsed = parse_json_or_fields(stdout + "\n" + stderr)
    return {
        "ok": rc == 0,
        "gen_status": parsed.get("gen_status"),
        "fail_reason": parsed.get("fail_reason"),
        "estimated_remaining_seconds": parsed.get("estimated_remaining_seconds"),
        "downloaded_files": [str(p) for p in sorted(after)],
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def cmd_query(args: argparse.Namespace) -> None:
    exe = resolve_dreamina()
    task_dir = Path(args.task_dir).expanduser().resolve()
    state_file = task_dir / "dreamina_task.json"
    submit_id = args.submit_id
    state: dict[str, Any] = {}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        submit_id = submit_id or state.get("submit_id")
    if not submit_id:
        raise ValueError(f"未提供 --submit-id，且 {state_file} 中无 submit_id。")

    if args.download:
        info = _download_result(exe, submit_id, task_dir)
    else:
        rc, stdout, stderr = run_cli([exe, "query_result", f"--submit_id={submit_id}"], timeout=60)
        parsed = parse_json_or_fields(stdout + "\n" + stderr)
        info = {
            "ok": rc == 0,
            "gen_status": parsed.get("gen_status"),
            "fail_reason": parsed.get("fail_reason"),
            "estimated_remaining_seconds": parsed.get("estimated_remaining_seconds"),
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }

    if state_file.exists():
        state["gen_status"] = info.get("gen_status") or state.get("gen_status")
        state["last_query_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if info.get("downloaded_files"):
            state["downloaded_files"] = info["downloaded_files"]
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"submit_id": submit_id, **info}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="即梦（Dreamina）官方 CLI 防呆调度器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查 dreamina CLI 可用性与当前积分余额")

    p_sub = sub.add_parser("submit", help="防重提交视频生成任务并落盘 submit_id")
    p_sub.add_argument("--task-dir", required=True, help="任务目录（保存 dreamina_task.json 与下载原片）")
    p_sub.add_argument(
        "--mode",
        choices=["text2video", "image2video", "frames2video", "multimodal2video"],
        default="text2video",
    )
    p_sub.add_argument("--prompt", required=True, help="生成提示词")
    p_sub.add_argument("--duration", type=int, default=5, help="时长（秒，默认 5s 省积分）")
    p_sub.add_argument("--ratio", default="9:16", help="画面比例（默认 9:16 竖屏；seedance2.5 图生视频请传空字符串省略）")
    p_sub.add_argument("--video-resolution", default="720p", help="分辨率（默认 720p）")
    p_sub.add_argument("--model-version", default="", help="可选模型版本（留空使用 CLI 当前默认）")
    p_sub.add_argument("--image", default="", help="图生视频主参考图路径")
    p_sub.add_argument("--poll", type=int, default=60, help="提交后最多轮询秒数（默认 60s）")
    p_sub.add_argument("--auto-download", action="store_true", help="轮询成功时立刻下载原片")
    p_sub.add_argument("--force-new", action="store_true", help="忽略目录内已有 submit_id 强制新提交")
    p_sub.add_argument("--extra", nargs="*", help="透传给 dreamina CLI 的其他参数")

    p_q = sub.add_parser("query", help="按已保存的 submit_id 续查进度并下载")
    p_q.add_argument("--task-dir", required=True, help="任务目录")
    p_q.add_argument("--submit-id", default="", help="可选，显式指定 submit_id")
    p_q.add_argument("--download", action="store_true", help="完成后通过 --download_dir 下载原片")

    args = parser.parse_args()
    if args.cmd == "check":
        cmd_check()
    elif args.cmd == "submit":
        cmd_submit(args)
    elif args.cmd == "query":
        cmd_query(args)


if __name__ == "__main__":
    main()
