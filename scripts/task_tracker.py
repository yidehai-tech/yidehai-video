#!/usr/bin/env python3
"""
亿德海跨 Agent 共用任务台账与本地静态仪表盘（纯标准库，零外部依赖，零后台服务）

单一事实源（固定位于 ~/.yidehai-video/，与 config.json / used_history.json 同级）：
  - ~/.yidehai-video/tasks.json       : 全 10 大轨道任务生命周期台账（带跨进程文件锁 + 原子写入）
  - ~/.yidehai-video/dashboard.html   : 自动刷新的纯离线可视化仪表盘（双击浏览器直接查看，无需起服务）

设计红线：
  1. Best-Effort 非阻塞：出片脚本调用 safe_start_task / safe_finish_task / safe_record_task 时，任何记账异常绝不影响已渲染成片；
  2. 僵尸 running 自愈：超 30 分钟且所属 PID 已退出的 running 任务，读取时自动标为 interrupted（中断待续渲）；
  3. 严格防 XSS：内嵌 JSON 转义 </ 为 <\\/，前端渲染全部使用 textContent，默认展示最近 200 条防卡顿。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import media_manager  # noqa: E402

TASKS_PATH = media_manager.APP_DIR / "tasks.json"
DASHBOARD_PATH = media_manager.APP_DIR / "dashboard.html"
LOCK_PATH = media_manager.APP_DIR / "tasks.lock"

VALID_STATUSES = (
    "pending_render",
    "running",
    "done",
    "failed",
    "interrupted",
    "published",
    "discarded",
)

TRACK_LABELS = {
    "poster": "大字报",
    "motion": "动效片",
    "montage": "实拍混剪",
    "fastcut": "实拍快剪",
    "before_after": "前后对比片",
    "storybook": "图文故事片",
    "dreamina": "即梦片",
    "flow": "Flow片",
    "api_video": "API片",
    "motiongit": "口播包装",
    "other": "其他",
}

STALE_RUNNING_SECONDS = 1800  # 30 分钟


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _today_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def detect_agent_host(explicit: str = "") -> str:
    """尽量温和识别当前宿主，不强猜不误报。"""
    if explicit and explicit.strip():
        return explicit.strip()
    env_host = os.environ.get("YIDEHAI_AGENT_HOST", "").strip()
    if env_host:
        return env_host
    probe = " ".join([
        str(Path.cwd()),
        str(SCRIPT_DIR),
        os.environ.get("TERM_PROGRAM", ""),
    ]).lower()
    markers = [
        ("agent_mode", "doubao"),
        ("doubao", "doubao"),
        (".workbuddy", "workbuddy"),
        ("workbuddy", "workbuddy"),
        (".claude", "claude-code"),
        (".codex", "codex"),
        (".cursor", "cursor"),
        (".trae", "trae"),
        (".windsurf", "windsurf"),
        (".gemini", "antigravity"),
        (".openclaw", "openclaw"),
    ]
    for needle, name in markers:
        if needle in probe:
            return name
    return "local"


def _to_file_uri(path_str: str) -> str:
    if not path_str:
        return ""
    s = path_str.replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        return "file:///" + quote(s, safe="/:")
    if s.startswith("/"):
        return "file://" + quote(s, safe="/:")
    return ""


def _parse_iso(ts: str) -> float:
    try:
        return datetime.datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def _load_unlocked() -> dict[str, Any]:
    if TASKS_PATH.exists():
        try:
            data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tasks"), list):
                return data
        except Exception:
            pass
    return {"schema_version": "1.0", "updated_at": _now_iso(), "tasks": []}


def _heal_stale_running(data: dict[str, Any]) -> bool:
    """将超 30 分钟且所属进程已退出的僵尸 running 任务自动修正为 interrupted。"""
    changed = False
    now_ts = datetime.datetime.now().timestamp()
    for t in data.get("tasks", []):
        if t.get("status") != "running":
            continue
        pid = int(t.get("pid") or 0)
        started_ts = _parse_iso(str(t.get("started_at") or t.get("updated_at") or ""))
        age = (now_ts - started_ts) if started_ts > 0 else STALE_RUNNING_SECONDS + 1
        if age > STALE_RUNNING_SECONDS and not media_manager._pid_alive(pid):
            t["status"] = "interrupted"
            t["updated_at"] = _now_iso()
            if not t.get("note"):
                t["note"] = "渲染进程疑似异常中断，已自动标记为中断待续渲。"
            changed = True
    return changed


def _save_unlocked(data: dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    media_manager.atomic_write_json(TASKS_PATH, data)
    render_dashboard_html(data, DASHBOARD_PATH)


def start_task(
    track: str,
    title: str,
    slug: str = "",
    out_dir: str = "",
    agent: str = "",
    note: str = "",
    copy_text: str = "",
) -> str:
    task_id = f"T-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    now = _now_iso()
    norm_track = track if track in TRACK_LABELS else "other"
    entry: dict[str, Any] = {
        "task_id": task_id,
        "track": norm_track,
        "track_zh": TRACK_LABELS[norm_track],
        "title": (title or slug or norm_track).strip()[:120],
        "slug": slug.strip(),
        "status": "running",
        "agent": detect_agent_host(agent),
        "pid": os.getpid(),
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        "elapsed_sec": None,
        "duration_sec": None,
        "out_dir": str(out_dir or ""),
        "video": "",
        "cover_9x16": "",
        "cover_3x4": "",
        "bgm": "",
        "copy_text": (copy_text or "").strip()[:1000],
        "error": "",
        "note": (note or "").strip()[:400],
    }
    with media_manager.file_lock(LOCK_PATH, timeout=10.0):
        data = _load_unlocked()
        _heal_stale_running(data)
        data["tasks"].insert(0, entry)
        _save_unlocked(data)
    return task_id


def finish_task(
    task_id: str,
    status: str = "done",
    video: str = "",
    cover_9x16: str = "",
    cover_3x4: str = "",
    duration_sec: float | None = None,
    bgm: str = "",
    error: str = "",
    note: str = "",
    copy_text: str = "",
    out_dir: str = "",
) -> dict[str, Any] | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"不支持的状态：{status}，可选：{VALID_STATUSES}")
    with media_manager.file_lock(LOCK_PATH, timeout=10.0):
        data = _load_unlocked()
        _heal_stale_running(data)
        target = next((t for t in data["tasks"] if t.get("task_id") == task_id), None)
        if target is None:
            return None
        now = _now_iso()
        target["status"] = status
        target["updated_at"] = now
        started_ts = _parse_iso(str(target.get("started_at") or ""))
        if started_ts > 0 and target.get("elapsed_sec") is None and status in {"done", "failed", "pending_render"}:
            target["elapsed_sec"] = round(max(0.0, datetime.datetime.now().timestamp() - started_ts), 1)
        if video:
            target["video"] = str(video)
        if cover_9x16:
            target["cover_9x16"] = str(cover_9x16)
        if cover_3x4:
            target["cover_3x4"] = str(cover_3x4)
        if duration_sec is not None:
            target["duration_sec"] = round(float(duration_sec), 2)
        if bgm:
            target["bgm"] = str(bgm)
        if error:
            target["error"] = str(error).strip()[-500:]
        if note:
            target["note"] = str(note).strip()[:400]
        if copy_text:
            target["copy_text"] = str(copy_text).strip()[:1000]
        if out_dir:
            target["out_dir"] = str(out_dir)
        _save_unlocked(data)
        return target


def record_task(
    track: str,
    title: str,
    status: str = "pending_render",
    slug: str = "",
    out_dir: str = "",
    video: str = "",
    cover_9x16: str = "",
    cover_3x4: str = "",
    duration_sec: float | None = None,
    bgm: str = "",
    agent: str = "",
    error: str = "",
    note: str = "",
    copy_text: str = "",
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"不支持的状态：{status}，可选：{VALID_STATUSES}")
    tid = start_task(track=track, title=title, slug=slug, out_dir=out_dir, agent=agent, note=note, copy_text=copy_text)
    if status != "running":
        res = finish_task(
            tid,
            status=status,
            video=video,
            cover_9x16=cover_9x16,
            cover_3x4=cover_3x4,
            duration_sec=duration_sec,
            bgm=bgm,
            error=error,
            note=note,
            copy_text=copy_text,
            out_dir=out_dir,
        )
        return res or {"task_id": tid, "status": status}
    return {"task_id": tid, "status": "running"}


def safe_start_task(**kwargs: Any) -> str:
    """Best-Effort 非阻塞入口：供出片脚本调用，失败绝不中断主流程。"""
    try:
        return start_task(**kwargs)
    except Exception:
        return ""


def safe_finish_task(task_id: str, **kwargs: Any) -> None:
    """Best-Effort 非阻塞收口：供出片脚本调用，失败绝不中断主流程。"""
    if not task_id:
        return
    try:
        finish_task(task_id, **kwargs)
    except Exception:
        pass


def safe_record_task(**kwargs: Any) -> None:
    """Best-Effort 非阻塞单步补录：供批量待续渲等场景调用，失败绝不中断主流程。"""
    try:
        record_task(**kwargs)
    except Exception:
        pass


def compute_summary(data: dict[str, Any]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = data.get("tasks", [])
    today = _today_str()
    by_status: dict[str, int] = {s: 0 for s in VALID_STATUSES}
    by_track: dict[str, int] = {}
    today_total = 0
    for t in tasks:
        st = t.get("status", "done")
        by_status[st] = by_status.get(st, 0) + 1
        tr = t.get("track", "other")
        by_track[tr] = by_track.get(tr, 0) + 1
        if str(t.get("created_at", "")).startswith(today):
            today_total += 1
    finished_ok = by_status["done"] + by_status["published"]
    finished_all = finished_ok + by_status["failed"] + by_status["interrupted"]
    success_rate = round((finished_ok / finished_all) * 100, 1) if finished_all > 0 else 100.0
    actionable = [
        {
            "task_id": t["task_id"],
            "track_zh": t.get("track_zh", t.get("track")),
            "title": t.get("title"),
            "status": t.get("status"),
            "out_dir": t.get("out_dir"),
            "error": t.get("error") or t.get("note"),
            "updated_at": t.get("updated_at"),
        }
        for t in tasks
        if t.get("status") in {"pending_render", "failed", "interrupted"}
    ][:15]
    return {
        "ok": True,
        "tasks_path": str(TASKS_PATH),
        "dashboard_path": str(DASHBOARD_PATH),
        "total": len(tasks),
        "today_total": today_total,
        "success_rate_pct": success_rate,
        "by_status": by_status,
        "by_track": {TRACK_LABELS.get(k, k): v for k, v in sorted(by_track.items(), key=lambda kv: -kv[1])},
        "actionable_pending": actionable,
    }


def render_dashboard_html(data: dict[str, Any], out_html: Path) -> None:
    """生成纯静态单文件离线仪表盘（防 XSS、零外链 CDN、默认渲染最近 200 条）。"""
    tasks = data.get("tasks", [])[:200]
    safe_rows = []
    for t in tasks:
        row = dict(t)
        row["cover_uri"] = _to_file_uri(str(t.get("cover_9x16") or t.get("cover_3x4") or ""))
        row["video_uri"] = _to_file_uri(str(t.get("video") or ""))
        safe_rows.append(row)

    summary = compute_summary(data)
    payload = {
        "updated_at": data.get("updated_at") or _now_iso(),
        "total_all": len(data.get("tasks", [])),
        "showing": len(safe_rows),
        "summary": summary,
        "tasks": safe_rows,
    }
    # 防止 </script> 注入破坏 HTML
    json_blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>亿德海视频生产台账与仪表盘</title>
<style>
  :root {{
    --bg: #f5f7f6; --card: #ffffff; --text: #1b2420; --muted: #5f6f67;
    --line: #e2e8e4; --brand: #1f7a4c; --brand-soft: #e9f5ee;
    --warn: #b7791f; --warn-soft: #fef6e4; --err: #c53030; --err-soft: #fdecec;
    --info: #2b6cb0; --info-soft: #ebf4ff;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); }}
  .wrap {{ max-width: 1220px; margin: 0 auto; padding: 24px 20px 48px; }}
  header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 18px; }}
  h1 {{ margin: 0; font-size: 22px; }}
  .sub {{ color: var(--muted); font-size: 13px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 12px; margin-bottom: 18px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }}
  .kpi .label {{ font-size: 12px; color: var(--muted); }}
  .kpi .val {{ font-size: 26px; font-weight: 700; margin-top: 6px; }}
  .panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
  .panel h2 {{ margin: 0 0 12px; font-size: 15px; }}
  .bars {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px 18px; }}
  .bar-row {{ font-size: 13px; }}
  .bar-head {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
  .bar-track {{ height: 8px; background: #edf2ef; border-radius: 99px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: var(--brand); border-radius: 99px; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; align-items: center; }}
  .filters select, .filters input {{ padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; font-size: 13px; }}
  .filters input {{ flex: 1; min-width: 180px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
  th {{ color: var(--muted); font-weight: 600; font-size: 12px; }}
  .thumb {{ width: 42px; height: 74px; object-fit: cover; border-radius: 6px; background: #edf2ef; display: block; }}
  .thumb-empty {{ width: 42px; height: 74px; border-radius: 6px; background: #edf2ef; color: var(--muted); font-size: 11px; display: flex; align-items: center; justify-content: center; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 12px; font-weight: 600; white-space: nowrap; }}
  .st-done {{ background: var(--brand-soft); color: var(--brand); }}
  .st-published {{ background: #dcfce7; color: #166534; }}
  .st-running {{ background: var(--info-soft); color: var(--info); }}
  .st-pending_render, .st-interrupted {{ background: var(--warn-soft); color: var(--warn); }}
  .st-failed {{ background: var(--err-soft); color: var(--err); }}
  .st-discarded {{ background: #edf2f7; color: #64748b; }}
  .meta {{ color: var(--muted); font-size: 12px; margin-top: 3px; word-break: break-all; }}
  .btn {{ border: 1px solid var(--line); background: #fff; padding: 4px 8px; border-radius: 6px; cursor: pointer; font-size: 12px; margin-right: 4px; margin-top: 4px; }}
  .btn:hover {{ background: var(--brand-soft); border-color: var(--brand); color: var(--brand); }}
  .toast {{ position: fixed; right: 20px; bottom: 20px; background: #1b2420; color: #fff; padding: 8px 14px; border-radius: 8px; font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; }}
  .toast.show {{ opacity: 1; }}
  .empty {{ text-align: center; padding: 28px; color: var(--muted); }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>亿德海短视频生产台账（跨 Agent 共享）</h1>
    <div class="sub" id="updatedAt"></div>
  </header>
  <section class="kpis" id="kpis"></section>
  <section class="panel">
    <h2>各视频形态产出分布</h2>
    <div class="bars" id="trackBars"></div>
  </section>
  <section class="panel">
    <div class="filters">
      <select id="fStatus">
        <option value="">全部状态</option>
        <option value="done">已成片</option>
        <option value="published">已发布</option>
        <option value="pending_render">待续渲</option>
        <option value="interrupted">中断待续渲</option>
        <option value="failed">失败待修</option>
        <option value="running">渲染中</option>
        <option value="discarded">已废弃</option>
      </select>
      <select id="fTrack"><option value="">全部形态</option></select>
      <input id="fQuery" placeholder="搜索标题 / ID / 错误信息 / Agent..." />
      <span class="sub" id="countHint"></span>
    </div>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>封面</th><th>标题与产物</th><th>形态</th><th>状态</th><th>时长/耗时</th><th>来源与时间</th><th>快捷操作</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </section>
</div>
<div class="toast" id="toast">已复制</div>
<script type="application/json" id="tasks-data">{json_blob}</script>
<script>
const STATUS_ZH = {{
  done: "已成片", published: "已发布", running: "渲染中",
  pending_render: "待续渲", interrupted: "中断待续渲", failed: "失败待修", discarded: "已废弃"
}};
const DATA = JSON.parse(document.getElementById("tasks-data").textContent);

function showToast(msg) {{
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 1600);
}}

function copyText(txt, label) {{
  if (!txt) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(txt).then(() => showToast("已复制" + label)).catch(() => fallbackCopy(txt, label));
  }} else {{
    fallbackCopy(txt, label);
  }}
}}

function fallbackCopy(txt, label) {{
  const ta = document.createElement("textarea");
  ta.value = txt;
  document.body.appendChild(ta);
  ta.select();
  try {{ document.execCommand("copy"); showToast("已复制" + label); }} catch (e) {{}}
  document.body.removeChild(ta);
}}

function el(tag, cls, text) {{
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}}

document.getElementById("updatedAt").textContent =
  "最近更新：" + DATA.updated_at + " · 共记录 " + DATA.total_all + " 条（展示最近 " + DATA.showing + " 条） · 修改状态可直接对任意 Agent 说「把某条标成已发布」";

const s = DATA.summary;
const pendingCnt = (s.by_status.pending_render || 0) + (s.by_status.failed || 0) + (s.by_status.interrupted || 0);
const kpiItems = [
  ["累计任务", s.total],
  ["今日新增", s.today_total],
  ["已成片", s.by_status.done || 0],
  ["已发布", s.by_status.published || 0],
  ["待修/待续渲", pendingCnt],
  ["成片成功率", s.success_rate_pct + "%"]
];
const kpisEl = document.getElementById("kpis");
kpiItems.forEach(([label, val]) => {{
  const box = el("div", "kpi");
  box.appendChild(el("div", "label", label));
  box.appendChild(el("div", "val", val));
  kpisEl.appendChild(box);
}});

const barsEl = document.getElementById("trackBars");
const trackEntries = Object.entries(s.by_track || {{}});
const maxTrack = Math.max(1, ...trackEntries.map(([, v]) => v));
const fTrack = document.getElementById("fTrack");
if (trackEntries.length === 0) {{
  barsEl.appendChild(el("div", "sub", "暂无生产记录"));
}} else {{
  trackEntries.forEach(([name, cnt]) => {{
    const opt = el("option", "", name);
    opt.value = name;
    fTrack.appendChild(opt);
    const row = el("div", "bar-row");
    const head = el("div", "bar-head");
    head.appendChild(el("span", "", name));
    head.appendChild(el("span", "", cnt + " 条"));
    const track = el("div", "bar-track");
    const fill = el("div", "bar-fill");
    fill.style.width = Math.round((cnt / maxTrack) * 100) + "%";
    track.appendChild(fill);
    row.appendChild(head);
    row.appendChild(track);
    barsEl.appendChild(row);
  }});
}}

function renderTable() {{
  const st = document.getElementById("fStatus").value;
  const tr = document.getElementById("fTrack").value;
  const q = document.getElementById("fQuery").value.trim().toLowerCase();
  const list = DATA.tasks.filter(t => {{
    if (st && t.status !== st) return false;
    if (tr && (t.track_zh || t.track) !== tr) return false;
    if (q) {{
      const hay = [t.title, t.task_id, t.slug, t.agent, t.error, t.note, t.video].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});
  document.getElementById("countHint").textContent = "匹配 " + list.length + " 条";
  const tb = document.getElementById("tbody");
  tb.textContent = "";
  if (list.length === 0) {{
    const trEl = el("tr");
    const td = el("td", "empty", "暂无符合条件的任务记录");
    td.colSpan = 7;
    trEl.appendChild(td);
    tb.appendChild(trEl);
    return;
  }}
  list.forEach(t => {{
    const row = el("tr");
    const tdImg = el("td");
    if (t.cover_uri) {{
      const img = el("img", "thumb");
      img.loading = "lazy";
      img.src = t.cover_uri;
      img.alt = t.title || "";
      img.onerror = () => {{ img.replaceWith(el("div", "thumb-empty", "无图")); }};
      tdImg.appendChild(img);
    }} else {{
      tdImg.appendChild(el("div", "thumb-empty", "无图"));
    }}
    row.appendChild(tdImg);

    const tdTitle = el("td");
    tdTitle.appendChild(el("div", "", t.title || t.slug || t.task_id));
    tdTitle.appendChild(el("div", "meta", t.task_id + (t.video ? " · " + t.video : (t.out_dir ? " · " + t.out_dir : ""))));
    if (t.error || t.note) {{
      tdTitle.appendChild(el("div", "meta", (t.error ? "错误：" + t.error : t.note)));
    }}
    row.appendChild(tdTitle);

    row.appendChild(el("td", "", t.track_zh || t.track));

    const tdSt = el("td");
    tdSt.appendChild(el("span", "badge st-" + t.status, STATUS_ZH[t.status] || t.status));
    row.appendChild(tdSt);

    const durTxt = (t.duration_sec ? t.duration_sec + "s" : "-") + " / " + (t.elapsed_sec !== null && t.elapsed_sec !== undefined ? t.elapsed_sec + "s" : "-");
    row.appendChild(el("td", "", durTxt));

    const tdMeta = el("td");
    tdMeta.appendChild(el("div", "", t.agent || "local"));
    tdMeta.appendChild(el("div", "meta", (t.updated_at || t.created_at || "").replace("T", " ").slice(0, 19)));
    row.appendChild(tdMeta);

    const tdAct = el("td");
    if (t.video) {{
      const b1 = el("button", "btn", "复制视频路径");
      b1.onclick = () => copyText(t.video, "视频路径");
      tdAct.appendChild(b1);
    }}
    if (t.copy_text) {{
      const b2 = el("button", "btn", "复制文案");
      b2.onclick = () => copyText(t.copy_text, "发布文案");
      tdAct.appendChild(b2);
    }}
    const b3 = el("button", "btn", "复制已发布指令");
    b3.onclick = () => copyText("请把任务 " + t.task_id + " 标记为已发布", "状态更新指令");
    tdAct.appendChild(b3);
    row.appendChild(tdAct);

    tb.appendChild(row);
  }});
}}

document.getElementById("fStatus").addEventListener("change", renderTable);
document.getElementById("fTrack").addEventListener("change", renderTable);
document.getElementById("fQuery").addEventListener("input", renderTable);
renderTable();
</script>
</body>
</html>
"""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_html.with_suffix(".html.tmp")
    tmp.write_text(html_doc, encoding="utf-8")
    os.replace(tmp, out_html)


def main() -> None:
    parser = argparse.ArgumentParser(description="亿德海跨 Agent 共用任务台账与本地仪表盘工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("summary", help="输出统计摘要与待处理/待续渲任务列表")

    p_list = sub.add_parser("list", help="列出任务明细")
    p_list.add_argument("--status", choices=VALID_STATUSES, default="")
    p_list.add_argument("--track", choices=list(TRACK_LABELS.keys()), default="")
    p_list.add_argument("--limit", type=int, default=30)

    p_rec = sub.add_parser("record", help="手动补录一条任务（如离线续渲包 / 纯对话脚本）")
    p_rec.add_argument("--track", choices=list(TRACK_LABELS.keys()), required=True)
    p_rec.add_argument("--title", required=True)
    p_rec.add_argument("--status", choices=VALID_STATUSES, default="pending_render")
    p_rec.add_argument("--slug", default="")
    p_rec.add_argument("--out-dir", default="")
    p_rec.add_argument("--video", default="")
    p_rec.add_argument("--cover-9x16", default="")
    p_rec.add_argument("--agent", default="")
    p_rec.add_argument("--note", default="")
    p_rec.add_argument("--copy-text", default="")

    p_upd = sub.add_parser("update", help="更新指定任务状态（如标为 published / discarded / done）")
    p_upd.add_argument("--id", required=True, help="任务 ID（如 T-20261126-...）")
    p_upd.add_argument("--status", choices=VALID_STATUSES, required=True)
    p_upd.add_argument("--note", default="")
    p_upd.add_argument("--video", default="")

    sub.add_parser("rebuild", help="重新生成本地静态仪表盘 dashboard.html")

    args = parser.parse_args()

    if args.cmd == "summary":
        with media_manager.file_lock(LOCK_PATH, timeout=10.0):
            data = _load_unlocked()
            if _heal_stale_running(data) or not DASHBOARD_PATH.exists():
                _save_unlocked(data)
        print(json.dumps(compute_summary(data), ensure_ascii=False, indent=2))

    elif args.cmd == "list":
        with media_manager.file_lock(LOCK_PATH, timeout=10.0):
            data = _load_unlocked()
            if _heal_stale_running(data):
                _save_unlocked(data)
        rows = data.get("tasks", [])
        if args.status:
            rows = [r for r in rows if r.get("status") == args.status]
        if args.track:
            rows = [r for r in rows if r.get("track") == args.track]
        print(json.dumps({"ok": True, "count": len(rows[: args.limit]), "tasks": rows[: args.limit]}, ensure_ascii=False, indent=2))

    elif args.cmd == "record":
        row = record_task(
            track=args.track,
            title=args.title,
            status=args.status,
            slug=args.slug,
            out_dir=args.out_dir,
            video=args.video,
            cover_9x16=args.cover_9x16,
            agent=args.agent,
            note=args.note,
            copy_text=args.copy_text,
        )
        print(json.dumps({"ok": True, "task": row, "dashboard_path": str(DASHBOARD_PATH)}, ensure_ascii=False, indent=2))

    elif args.cmd == "update":
        row = finish_task(args.id, status=args.status, note=args.note, video=args.video)
        if row is None:
            print(json.dumps({"ok": False, "error": f"未找到任务 {args.id}"}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps({"ok": True, "task": row, "dashboard_path": str(DASHBOARD_PATH)}, ensure_ascii=False, indent=2))

    elif args.cmd == "rebuild":
        with media_manager.file_lock(LOCK_PATH, timeout=10.0):
            data = _load_unlocked()
            _heal_stale_running(data)
            _save_unlocked(data)
        print(json.dumps({"ok": True, "dashboard_path": str(DASHBOARD_PATH), "total": len(data.get("tasks", []))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
