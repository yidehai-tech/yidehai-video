#!/usr/bin/env python3
"""
亿德海「动效片」三套高转化 HyperFrames / OpenMotion HTML+GSAP 母版生成器
严格遵守 knowledge/06-rendering-playbook.md 全部 lint 硬要求：
- 必须声明 @font-face (local 中文字体)
- 顶层 index.html 拆子合成到 compositions/film.html (data-composition-src)
- 同一元素不叠两条 fromTo
- 首帧 0.05s 内饱满呈现，无长淡入留白
- 结尾仅叠加方案 A 轻量半透明品牌浮条，绝无全屏静态尾卡

三套内置样式（支持自动轮换）：
1. chat      —— 手机/微信聊天气泡版（生活感极强、完播率最高）
2. checklist —— 清单打勾 + 大字数字跳动 + 痛点红叉划掉版（避坑/干货/科普神器）
3. kinetic   —— 动能大字卡点 + 扫光高亮 + 镜头推进转场版（强节奏视觉冲击）
"""

import html
import re
from pathlib import Path

STYLES = ("chat", "checklist", "kinetic")

STYLE_ALIASES = {
    "chat": "chat",
    "聊天气泡": "chat",
    "微信对话": "chat",
    "对话": "chat",
    "checklist": "checklist",
    "清单打勾": "checklist",
    "清单": "checklist",
    "数字跳动": "checklist",
    "避坑": "checklist",
    "kinetic": "kinetic",
    "动能大字": "kinetic",
    "卡点": "kinetic",
}

FONT_FACE_CSS = """
    @font-face {
      font-family: "YidehaiSans";
      src: local("PingFang SC"), local("Microsoft YaHei"), local("Hiragino Sans GB"), local("SimHei");
      font-weight: 400 900;
    }
"""


def normalize_motion_style(raw: str | None, fallback_index: int = 0) -> str:
    if raw:
        key = raw.strip().lower()
        if key in STYLE_ALIASES:
            return STYLE_ALIASES[key]
    return STYLES[fallback_index % len(STYLES)]


def _extract_lines(item: dict) -> list[str]:
    raw_body = item.get("body", [])
    if isinstance(raw_body, list):
        return [str(x).strip() for x in raw_body if str(x).strip()]
    return [l.strip() for l in str(raw_body).splitlines() if l.strip()]


def _write_root_index(proj_dir: Path, title: str, duration: float, bg_color: str) -> None:
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>{html.escape(title)}</title>
  <style>
{FONT_FACE_CSS}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; background: {bg_color}; font-family: "YidehaiSans", sans-serif; }}
  </style>
</head>
<body>
  <div id="root" data-composition-id="root" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div data-track="main" data-start="0" data-duration="{duration:.2f}" data-composition-src="compositions/film.html"></div>
  </div>
</body>
</html>
"""
    (proj_dir / "index.html").write_text(index_html, encoding="utf-8")


def _build_chat_film(item: dict, duration: float) -> str:
    title = html.escape(str(item.get("title", "衣柜塞爆了怎么办？")).replace("\n", " "))
    lines = _extract_lines(item)
    question = str(item.get("question", "")).strip()
    pill = html.escape(str(item.get("pill", "亿德海 · 专人免费上门回收")))

    # 支持显式 messages，否则自动把正文转为自然 5 轮手机对话气泡
    raw_msgs = item.get("messages")
    if isinstance(raw_msgs, list) and raw_msgs:
        msgs = [(m.get("side", "left"), str(m.get("text", "")).strip()) for m in raw_msgs[:6] if m.get("text")]
    else:
        chunks = []
        if len(lines) >= 4:
            step = max(1, len(lines) // 4)
            for i in range(0, len(lines), step):
                chunks.append("".join(lines[i:i + step]))
            chunks = chunks[:4]
        else:
            chunks = lines or ["换季衣柜塞爆了，好多旧衣服旧鞋子扔了可惜，扛下楼又太沉！"]
        msgs = []
        for idx, c in enumerate(chunks):
            msgs.append(("left" if idx % 2 == 0 else "right", c))
        if question:
            msgs.append(("left", question))

    bubble_html = []
    tween_lines = []
    t_cursor = 0.08
    gap = min(1.55, max(0.95, (duration - 2.6) / max(1, len(msgs))))

    for i, (side, text) in enumerate(msgs):
        cls = "msg-row left" if side == "left" else "msg-row right"
        avatar = "闺" if side == "left" else "我"
        av_cls = "av av-l" if side == "left" else "av av-r"
        bubble_html.append(
            f'<div class="{cls} m{i}">'
            f'<div class="{av_cls}">{avatar}</div>'
            f'<div class="bubble">{html.escape(text)}</div>'
            f'</div>'
        )
        tween_lines.append(
            f'tl.to(".m{i}", {{ opacity: 1, y: 0, scale: 1, duration: 0.42, ease: "back.out(1.45)" }}, {t_cursor:.2f});'
        )
        t_cursor += gap

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <style>
{FONT_FACE_CSS}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; background: linear-gradient(160deg, #0E261F 0%, #163A2E 52%, #0B1B16 100%); }}
    .glow {{ position: absolute; width: 760px; height: 760px; border-radius: 50%; background: radial-gradient(circle, rgba(255,212,59,0.18) 0%, rgba(255,212,59,0) 70%); top: -120px; left: 160px; }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 140px 58px 230px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; }}
    .top-banner {{ width: 100%; text-align: center; font-size: 64px; font-weight: 900; line-height: 1.24; color: #FFD43B; text-shadow: 0 6px 20px rgba(0,0,0,0.5); }}
    .phone {{ width: 960px; flex: 1; margin: 34px 0 32px; background: #EDEDED; border-radius: 44px; box-shadow: 0 28px 70px rgba(0,0,0,0.52); overflow: hidden; display: flex; flex-direction: column; border: 6px solid rgba(255,255,255,0.22); }}
    .phone-bar {{ background: #F7F7F7; padding: 26px 36px; border-bottom: 2px solid #DFDFDF; display: flex; align-items: center; justify-content: space-between; color: #1A1A1A; font-size: 38px; font-weight: 800; }}
    .phone-dot {{ width: 16px; height: 16px; border-radius: 50%; background: #2F9E44; display: inline-block; margin-right: 12px; }}
    .chat-body {{ flex: 1; padding: 34px 28px; display: flex; flex-direction: column; gap: 28px; overflow: hidden; }}
    .msg-row {{ display: flex; align-items: flex-start; gap: 18px; opacity: 0; transform: translateY(34px) scale(0.94); }}
    .msg-row.right {{ flex-direction: row-reverse; }}
    .av {{ width: 78px; height: 78px; border-radius: 18px; display: flex; align-items: center; justify-content: center; font-size: 34px; font-weight: 900; color: #FFF; flex-shrink: 0; }}
    .av-l {{ background: #3B5BDB; }}
    .av-r {{ background: #2B8A3E; }}
    .bubble {{ max-width: 720px; padding: 24px 30px; border-radius: 24px; font-size: 40px; font-weight: 700; line-height: 1.4; color: #161616; box-shadow: 0 6px 16px rgba(0,0,0,0.08); }}
    .msg-row.left .bubble {{ background: #FFFFFF; border-top-left-radius: 6px; }}
    .msg-row.right .bubble {{ background: #95EC69; border-top-right-radius: 6px; }}
    .pill {{ padding: 20px 52px; border-radius: 999px; background: rgba(0,0,0,0.62); border: 2px solid rgba(255,212,59,0.65); font-size: 38px; font-weight: 800; color: #FFFFFF; opacity: 0; transform: translateY(20px); }}
  </style>
</head>
<body>
  <div class="stage" data-composition-id="film" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div class="glow"></div>
    <div class="top-banner">{title}</div>
    <div class="phone">
      <div class="phone-bar"><span><span class="phone-dot"></span>居家断舍离交流</span><span style="color:#888;font-size:30px;">刚刚</span></div>
      <div class="chat-body">
        {''.join(bubble_html)}
      </div>
    </div>
    <div class="pill">{pill}</div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".glow", {{ x: 60, y: 40, duration: {duration:.2f}, ease: "none" }}, 0);
    {chr(10).join('    ' + line for line in tween_lines)}
    tl.to(".pill", {{ opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }}, {max(0.2, duration - 2.6):.2f});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""


def _build_checklist_film(item: dict, duration: float) -> str:
    title = html.escape(str(item.get("title", "卖旧衣服记住这3件事")).replace("\n", "\n"))
    lines = _extract_lines(item)
    question = html.escape(str(item.get("question", "按订单流程结算 · 干净省心")))
    pill = html.escape(str(item.get("pill", "亿德海 · 专人免费上门回收")))

    # 自动识别核心大数字（3 件 / 5 KG）
    joined = "".join(lines) + title
    if "羽绒服" in joined or "3件" in joined or "3 件" in joined:
        hero_num, hero_unit = "3", "件起收"
    else:
        hero_num, hero_unit = "5", "KG起收"

    # 拆 3-4 条清单项
    cards = lines[:4] if len(lines) >= 3 else (lines + ["专人免费上门 · 带秤当面称重", "回收款按订单流程结算"])[:3]
    card_html = []
    card_tweens = []
    for i, text in enumerate(cards):
        st = 1.65 + i * 1.35
        card_html.append(
            f'<div class="check-card c{i}">'
            f'<div class="chk">✓</div>'
            f'<div class="ctext">{html.escape(text)}</div>'
            f'</div>'
        )
        card_tweens.append(
            f'tl.to(".c{i}", {{ opacity: 1, x: 0, duration: 0.42, ease: "back.out(1.3)" }}, {st:.2f});'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <style>
{FONT_FACE_CSS}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; color: #FFF; background: #0C2019; }}
    .grid-bg {{ position: absolute; inset: -100px; background-image: linear-gradient(rgba(255,212,59,0.06) 2px, transparent 2px), linear-gradient(90deg, rgba(255,212,59,0.06) 2px, transparent 2px); background-size: 72px 72px; }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 155px 60px 230px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; }}
    .top-title {{ font-size: 74px; font-weight: 900; line-height: 1.22; text-align: center; color: #FFD43B; white-space: pre-line; text-shadow: 0 8px 24px rgba(0,0,0,0.5); }}
    .hero-metric {{ display: flex; align-items: baseline; justify-content: center; gap: 16px; background: rgba(255,212,59,0.14); border: 3px solid rgba(255,212,59,0.55); border-radius: 36px; padding: 26px 64px; transform: scale(0.85); opacity: 0; }}
    .hero-num {{ font-size: 132px; font-weight: 900; color: #FFD43B; line-height: 1; }}
    .hero-unit {{ font-size: 54px; font-weight: 800; color: #FFFFFF; }}
    .pain-badge {{ font-size: 38px; font-weight: 800; color: #FF8787; background: rgba(255,107,107,0.14); border: 2px solid rgba(255,107,107,0.45); padding: 14px 36px; border-radius: 999px; text-decoration: line-through; opacity: 0; transform: scale(0.9); }}
    .cards {{ width: 100%; display: flex; flex-direction: column; gap: 26px; }}
    .check-card {{ display: flex; align-items: center; gap: 26px; background: rgba(255,255,255,0.09); border: 2px solid rgba(255,255,255,0.18); border-radius: 28px; padding: 30px 34px; opacity: 0; transform: translateX(-60px); }}
    .chk {{ width: 68px; height: 68px; border-radius: 50%; background: #2F9E44; color: #FFF; font-size: 42px; font-weight: 900; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 6px 18px rgba(47,158,68,0.45); }}
    .ctext {{ font-size: 46px; font-weight: 800; line-height: 1.35; color: #FFFFFF; }}
    .question {{ font-size: 44px; font-weight: 800; color: #FFD43B; text-align: center; opacity: 0; }}
    .pill {{ padding: 20px 52px; border-radius: 999px; background: rgba(0,0,0,0.62); border: 2px solid rgba(255,212,59,0.65); font-size: 38px; font-weight: 800; color: #FFFFFF; opacity: 0; transform: translateY(20px); }}
  </style>
</head>
<body>
  <div class="stage" data-composition-id="film" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div class="grid-bg"></div>
    <div class="top-title">{title}</div>
    <div class="hero-metric"><span class="hero-num">{hero_num}</span><span class="hero-unit">{hero_unit}</span></div>
    <div class="pain-badge">✕ 自己扛下楼 · 乱扔占地方</div>
    <div class="cards">
      {''.join(card_html)}
    </div>
    <div class="question">{question}</div>
    <div class="pill">{pill}</div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".grid-bg", {{ x: 48, y: 48, duration: {duration:.2f}, ease: "none" }}, 0)
      .to(".hero-metric", {{ opacity: 1, scale: 1, duration: 0.45, ease: "back.out(1.6)" }}, 0.08)
      .to(".pain-badge", {{ opacity: 1, scale: 1, duration: 0.35, ease: "power2.out" }}, 0.75);
    {chr(10).join('    ' + line for line in card_tweens)}
    tl.to(".question", {{ opacity: 1, duration: 0.35 }}, {max(0.5, duration - 3.0):.2f})
      .to(".pill", {{ opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }}, {max(0.5, duration - 2.6):.2f});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""


def _build_kinetic_film(item: dict, duration: float) -> str:
    title = html.escape(str(item.get("title", "旧衣服别再塞爆衣柜")).replace("\n", "\n"))
    lines = _extract_lines(item)
    question = html.escape(str(item.get("question", "专人免费上门 · 当面称重")))
    pill = html.escape(str(item.get("pill", "亿德海 · 专人免费上门回收")))

    n = max(1, len(lines))
    b1 = html.escape("\n".join(lines[: max(1, n // 3)]))
    b2 = html.escape("\n".join(lines[max(1, n // 3): max(2, 2 * n // 3)]))
    b3 = html.escape("\n".join(lines[max(2, 2 * n // 3):]) or question)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <style>
{FONT_FACE_CSS}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; color: #FFF; background: #0B1D17; }}
    .orb1 {{ position: absolute; width: 680px; height: 680px; border-radius: 50%; background: radial-gradient(circle, rgba(47,158,68,0.34), transparent 70%); top: 120px; left: -120px; }}
    .orb2 {{ position: absolute; width: 620px; height: 620px; border-radius: 50%; background: radial-gradient(circle, rgba(255,212,59,0.24), transparent 70%); bottom: 180px; right: -100px; }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 170px 64px 240px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; text-align: center; }}
    .k-top {{ font-size: 76px; font-weight: 900; line-height: 1.2; color: #FFD43B; white-space: pre-line; text-shadow: 0 8px 24px rgba(0,0,0,0.5); }}
    .k-box {{ position: relative; width: 100%; height: 860px; display: flex; align-items: center; justify-content: center; }}
    .beat {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; opacity: 0; transform: scale(1.14) translateY(36px); }}
    .beat-text {{ font-size: 76px; font-weight: 900; line-height: 1.38; color: #FFFFFF; white-space: pre-line; text-shadow: 0 8px 28px rgba(0,0,0,0.55); }}
    .accent-bar {{ width: 0px; height: 14px; border-radius: 8px; background: #FFD43B; margin-top: 34px; }}
    .k-q {{ font-size: 46px; font-weight: 800; color: #FFD43B; opacity: 0; }}
    .pill {{ padding: 20px 52px; border-radius: 999px; background: rgba(0,0,0,0.62); border: 2px solid rgba(255,212,59,0.65); font-size: 38px; font-weight: 800; color: #FFFFFF; opacity: 0; transform: translateY(20px); }}
  </style>
</head>
<body>
  <div class="stage" data-composition-id="film" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div class="orb1"></div>
    <div class="orb2"></div>
    <div class="k-top">{title}</div>
    <div class="k-box">
      <div class="beat b1"><div class="beat-text">{b1}</div><div class="accent-bar ab1"></div></div>
      <div class="beat b2"><div class="beat-text">{b2}</div><div class="accent-bar ab2"></div></div>
      <div class="beat b3"><div class="beat-text">{b3}</div><div class="accent-bar ab3"></div></div>
    </div>
    <div class="k-q">{question}</div>
    <div class="pill">{pill}</div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".orb1", {{ x: 140, y: 100, duration: {duration:.2f}, ease: "none" }}, 0)
      .to(".orb2", {{ x: -120, y: -90, duration: {duration:.2f}, ease: "none" }}, 0)
      .to(".b1", {{ opacity: 1, scale: 1, y: 0, duration: 0.36, ease: "back.out(1.4)" }}, 0.05)
      .to(".ab1", {{ width: 320, duration: 0.45, ease: "power2.out" }}, 0.25)
      .to(".b1", {{ opacity: 0, scale: 0.88, y: -32, duration: 0.28, ease: "power2.in" }}, 3.15)
      .to(".b2", {{ opacity: 1, scale: 1, y: 0, duration: 0.36, ease: "back.out(1.4)" }}, 3.35)
      .to(".ab2", {{ width: 360, duration: 0.45, ease: "power2.out" }}, 3.55)
      .to(".b2", {{ opacity: 0, scale: 0.88, y: -32, duration: 0.28, ease: "power2.in" }}, 6.35)
      .to(".b3", {{ opacity: 1, scale: 1, y: 0, duration: 0.36, ease: "back.out(1.4)" }}, 6.55)
      .to(".ab3", {{ width: 400, duration: 0.45, ease: "power2.out" }}, 6.75)
      .to(".k-q", {{ opacity: 1, duration: 0.35 }}, 7.0)
      .to(".pill", {{ opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }}, {max(0.5, duration - 2.6):.2f});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""


def build_motion_project(item: dict, proj_dir: Path, fallback_index: int = 0) -> str:
    """按样式生成高转化动效片工程，返回实际选用的样式名（chat / checklist / kinetic）。"""
    proj_dir.mkdir(parents=True, exist_ok=True)
    comp_dir = proj_dir / "compositions"
    comp_dir.mkdir(exist_ok=True)

    style = normalize_motion_style(item.get("motion_style"), fallback_index=fallback_index)
    duration = float(item.get("duration", 10.0))
    title = str(item.get("title", "亿德海旧衣回收")).replace("\n", " ")

    if style == "chat":
        _write_root_index(proj_dir, title, duration, "#0E261F")
        film_html = _build_chat_film(item, duration)
    elif style == "checklist":
        _write_root_index(proj_dir, title, duration, "#0C2019")
        film_html = _build_checklist_film(item, duration)
    else:
        _write_root_index(proj_dir, title, duration, "#0B1D17")
        film_html = _build_kinetic_film(item, duration)

    (comp_dir / "film.html").write_text(film_html, encoding="utf-8")
    return style
