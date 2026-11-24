#!/usr/bin/env python3
"""
即梦（Dreamina）官方 CLI 防呆调度器（跨平台 macOS / Windows，纯标准库）

核心职责与防重复扣分保障（v2.4.0）：
  1. check  : 检查本机是否安装 dreamina CLI 并查询账号积分余额（user_credit）
  2. submit : 获取目录级跨进程锁 → 提交前先原子落盘 gen_status="submitting" 待确认记录 →
              提交任务并立即写回 submit_id；若 CLI 超时、异常退出或未解析到 submit_id，
              保留 uncertain 状态，禁止二次重复提交，必须先查 list_task 核实！
  3. query  : 按 dreamina_task.json 中的 submit_id 查询进度；gen_status=success 时通过
              --download_dir 无损下载成片原素材。若显式 --submit-id 与原记录不一致，拒绝覆盖原文件。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from media_manager import atomic_write_json, file_lock  # noqa: E402


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
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_json_or_fields(text: str) -> dict[str, Any]:
    text_s = text.strip()
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
        "dreamina_bin": Path(exe).name,
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
    lock_file = task_dir / ".dreamina.lock"

    with file_lock(lock_file, timeout=15.0):
        prev: dict[str, Any] | None = None
        if state_file.exists():
            try:
                prev = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                prev = {"gen_status": "corrupted_state"}

        if prev is not None and not args.force_new:
            prev_id = prev.get("submit_id")
            prev_status = prev.get("gen_status")
            print(json.dumps({
                "ok": False,
                "blocked": "EXISTING_TASK_STATE",
                "message": (
                    f"该任务目录已存在历史提交记录（status={prev_status}, submit_id={prev_id or '待核实'}）。"
                    "为防止重复扣积分已拦截新提交：请先运行 `query` 或 `dreamina list_task` 核实服务端状态；"
                    "只有在确认未扣分或已获明确新预算授权后，才可加 --force-new 重提。"
                ),
                "state_file": state_file.name,
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

        client_task_id = f"dm-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        attempts = list(prev.get("attempts", [])) if isinstance(prev, dict) else []
        if isinstance(prev, dict) and prev.get("client_task_id"):
            attempts.append({
                "client_task_id": prev.get("client_task_id"),
                "submit_id": prev.get("submit_id"),
                "gen_status": prev.get("gen_status"),
                "submitted_at": prev.get("submitted_at"),
            })

        # 提交前先原子落盘待确认状态（解决超时/中断无本地痕迹导致重复扣分的 P0 漏洞）
        record: dict[str, Any] = {
            "client_task_id": client_task_id,
            "mode": args.mode,
            "duration": args.duration,
            "ratio": args.ratio,
            "video_resolution": args.video_resolution,
            "model_version": args.model_version or "default",
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "submit_id": None,
            "gen_status": "submitting",
            "fail_reason": None,
            "estimated_remaining_seconds": None,
            "attempts": attempts,
        }
        atomic_write_json(state_file, record)

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

        try:
            rc, stdout, stderr = run_cli(cmd, timeout=max(120, (args.poll or 0) + 60))
        except subprocess.TimeoutExpired:
            record["gen_status"] = "uncertain_timeout"
            record["fail_reason"] = "CLI 等待超时，服务端可能已接单，请先执行 `dreamina list_task` 核实，禁止直接重试。"
            atomic_write_json(state_file, record)
            print(json.dumps({"ok": False, "gen_status": "uncertain_timeout", "message": record["fail_reason"]}, ensure_ascii=False, indent=2))
            sys.exit(1)

        parsed = parse_json_or_fields(stdout + "\n" + stderr)
        submit_id = parsed.get("submit_id")
        if submit_id:
            gen_status = parsed.get("gen_status") or ("submitted" if rc == 0 else "error")
        else:
            gen_status = "uncertain_no_id" if rc == 0 else "submit_failed_verify_list_task"

        record["submit_id"] = submit_id
        record["gen_status"] = gen_status
        record["fail_reason"] = parsed.get("fail_reason")
        record["estimated_remaining_seconds"] = parsed.get("estimated_remaining_seconds")
        record["returncode"] = rc
        atomic_write_json(state_file, record)

        result: dict[str, Any] = {
            "ok": rc == 0 and bool(submit_id),
            "client_task_id": client_task_id,
            "submit_id": submit_id,
            "gen_status": gen_status,
            "parsed": parsed,
        }
        combined = stdout + "\n" + stderr
        if "AigcComplianceConfirmationRequired" in combined:
            result["action_required"] = "该模型首次使用需先在即梦 Web 端完成一次合规确认生成，确认后再重试。"
        elif "ExceedConcurrencyLimit" in combined or "1310" in combined:
            result["action_required"] = "触发即梦并发限制，请勿重复提交，先用 list_task / query 检查排队任务。"

        if gen_status == "success" and submit_id and args.auto_download:
            result["download"] = _download_result(exe, submit_id, task_dir)

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
        "downloaded_files": [p.name for p in sorted(after)],
    }


def cmd_query(args: argparse.Namespace) -> None:
    exe = resolve_dreamina()
    task_dir = Path(args.task_dir).expanduser().resolve()
    state_file = task_dir / "dreamina_task.json"
    state: dict[str, Any] = {}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))

    saved_id = state.get("submit_id")
    if args.submit_id and saved_id and args.submit_id != saved_id:
        raise ValueError(
            f"显式传入的 --submit-id ({args.submit_id}) 与目录内保存的 submit_id ({saved_id}) 不一致，已拒绝覆盖原状态文件。"
        )
    submit_id = args.submit_id or saved_id
    if not submit_id:
        raise ValueError(f"未提供 --submit-id，且 {state_file.name} 中无 submit_id；请先运行 `dreamina list_task` 核实。")

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
        }

    if state_file.exists():
        with file_lock(task_dir / ".dreamina.lock", timeout=15.0):
            state["submit_id"] = submit_id
            state["gen_status"] = info.get("gen_status") or state.get("gen_status")
            state["last_query_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if info.get("downloaded_files"):
                state["downloaded_files"] = info["downloaded_files"]
            atomic_write_json(state_file, state)

    print(json.dumps({"submit_id": submit_id, **info}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="即梦（Dreamina）官方 CLI 防呆调度器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查 dreamina CLI 可用性与当前积分余额")

    p_sub = sub.add_parser("submit", help="防重提交视频生成任务并预先原子落盘")
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
    p_sub.add_argument("--force-new", action="store_true", help="确认未扣分或已获新预算授权后，归档旧尝试并新提交")
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
