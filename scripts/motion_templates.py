#!/usr/bin/env python3
"""
亿德海「动效片」三套高转化 HyperFrames / OpenMotion HTML+GSAP 母版生成器（v2.4.0）
严格遵守 knowledge/01-brand-rules.md、04-visual-style.md 与 06/09 全部硬要求：
- 必须声明 @font-face (local 中文字体)
- 顶层 index.html 拆子合成到 compositions/film.html (data-composition-src)
- 同一元素不叠两条 fromTo；首帧 0.05s 内饱满呈现，无长淡入留白
- 彻底移除底部品牌浮条与全屏静态尾卡，话音/信息结束即利落收尾
- 内置 5 套已验证浅色生活主题自动轮换（暖米橙 / 浅雾青 / 暖杏陶 / 浅暖金 / 淡薄荷），拒绝整批深绿发闷

三套内置样式（支持自动轮换）：
1. chat      —— 手机/微信聊天气泡版（生活感极强、完播率最高）
2. checklist —— 清单打勾 + 大字数字跳动 + 痛点红叉划掉版（避坑/干货/科普神器）
3. kinetic   —— 动能大字卡点 + 扫光高亮 + 动态比例切屏版（强节奏视觉冲击）
"""

import html
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

# 与 knowledge/04-visual-style.md §2.2 完全一致的 5 套浅色生活主题
LIGHT_THEMES = [
    {
        "name": "暖米橙",
        "bg1": "#FFFDF6", "bg2": "#F7F3E7", "bg3": "#EFE9DA",
        "stage1": "#FFFFFF", "stage2": "#F3EDE0",
        "ink": "#163026", "accent": "#E8590C", "accent2": "#F6A45C", "tag": "#3A5A48",
    },
    {
        "name": "浅雾青",
        "bg1": "#F4FBF7", "bg2": "#E7F3EC", "bg3": "#D9EBE1",
        "stage1": "#FFFFFF", "stage2": "#EAF4EE",
        "ink": "#173D2E", "accent": "#2B8A3E", "accent2": "#7CC08A", "tag": "#3C6150",
    },
    {
        "name": "暖杏陶",
        "bg1": "#FFF8F0", "bg2": "#FBEEDF", "bg3": "#F3E2CE",
        "stage1": "#FFFDF9", "stage2": "#F7EADA",
        "ink": "#3A2C20", "accent": "#D9603B", "accent2": "#F0A37E", "tag": "#6B5542",
    },
    {
        "name": "浅暖金",
        "bg1": "#FFFDF3", "bg2": "#FBF3DC", "bg3": "#F2E7C6",
        "stage1": "#FFFFFF", "stage2": "#F8F0D9",
        "ink": "#3B3218", "accent": "#D99412", "accent2": "#F5C65A", "tag": "#6A5B33",
    },
    {
        "name": "淡薄荷",
        "bg1": "#F2FAFA", "bg2": "#E4F2F1", "bg3": "#D3E9E8",
        "stage1": "#FFFFFF", "stage2": "#E8F4F3",
        "ink": "#123D3C", "accent": "#1E7A6E", "accent2": "#6FBDB2", "tag": "#37605E",
    },
]

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


def pick_light_theme(item: dict, fallback_index: int = 0) -> dict:
    wanted = str(item.get("color_theme") or "").strip()
    for th in LIGHT_THEMES:
        if th["name"] == wanted:
            return th
    return LIGHT_THEMES[fallback_index % len(LIGHT_THEMES)]


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
    * {{ box-sizing: border-box; }}
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


def _build_chat_film(item: dict, duration: float, th: dict) -> str:
    title = html.escape(str(item.get("title", "衣柜塞爆了怎么办？")).replace("\n", " "))
    lines = _extract_lines(item)
    question = str(item.get("question", "")).strip()

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
    gap = min(1.55, max(0.95, (duration - 1.4) / max(1, len(msgs))))

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
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; background: radial-gradient(120% 70% at 50% 6%, {th['bg1']} 0%, {th['bg2']} 46%, {th['bg3']} 100%); color: {th['ink']}; }}
    .glow {{ position: absolute; width: 760px; height: 760px; border-radius: 50%; background: radial-gradient(circle, {th['accent2']}33 0%, transparent 70%); top: -120px; left: 160px; }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 150px 58px 220px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; }}
    .top-banner {{ width: 100%; text-align: center; font-size: 62px; font-weight: 900; line-height: 1.26; color: {th['ink']}; text-shadow: 0 3px 0 rgba(255,255,255,0.85); }}
    .phone {{ width: 960px; flex: 1; margin-top: 38px; background: {th['stage1']}; border-radius: 44px; box-shadow: 0 28px 64px rgba(22,48,38,0.14); overflow: hidden; display: flex; flex-direction: column; border: 4px solid rgba(22,48,38,0.10); }}
    .phone-bar {{ background: {th['stage2']}; padding: 26px 36px; border-bottom: 2px solid rgba(22,48,38,0.08); display: flex; align-items: center; justify-content: space-between; color: {th['ink']}; font-size: 38px; font-weight: 800; }}
    .phone-dot {{ width: 16px; height: 16px; border-radius: 50%; background: {th['accent']}; display: inline-block; margin-right: 12px; }}
    .chat-body {{ flex: 1; padding: 34px 28px; display: flex; flex-direction: column; gap: 28px; overflow: hidden; background: {th['bg2']}; }}
    .msg-row {{ display: flex; align-items: flex-start; gap: 18px; opacity: 0; transform: translateY(34px) scale(0.94); }}
    .msg-row.right {{ flex-direction: row-reverse; }}
    .av {{ width: 78px; height: 78px; border-radius: 18px; display: flex; align-items: center; justify-content: center; font-size: 34px; font-weight: 900; color: #FFF; flex-shrink: 0; }}
    .av-l {{ background: {th['tag']}; }}
    .av-r {{ background: {th['accent']}; }}
    .bubble {{ max-width: 720px; padding: 24px 30px; border-radius: 24px; font-size: 40px; font-weight: 700; line-height: 1.4; color: {th['ink']}; box-shadow: 0 6px 16px rgba(22,48,38,0.08); }}
    .msg-row.left .bubble {{ background: #FFFFFF; border-top-left-radius: 6px; }}
    .msg-row.right .bubble {{ background: {th['accent']}; color: #FFFFFF; border-top-right-radius: 6px; }}
  </style>
</head>
<body>
  <div class="stage" data-composition-id="film" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div class="glow"></div>
    <div class="top-banner">{title}</div>
    <div class="phone">
      <div class="phone-bar"><span><span class="phone-dot"></span>居家断舍离交流</span><span style="color:{th['tag']};font-size:30px;">刚刚</span></div>
      <div class="chat-body">
        {''.join(bubble_html)}
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".glow", {{ x: 60, y: 40, duration: {duration:.2f}, ease: "none" }}, 0);
    {chr(10).join('    ' + line for line in tween_lines)}
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""


def _build_checklist_film(item: dict, duration: float, th: dict) -> str:
    title = html.escape(str(item.get("title", "卖旧衣服记住这3件事")).replace("\n", "\n"))
    lines = _extract_lines(item)
    question = html.escape(str(item.get("question", "按订单流程结算 · 干净省心")))

    joined = "".join(lines) + title
    if "羽绒服" in joined or "3件" in joined or "3 件" in joined:
        hero_num, hero_unit = "3", "件起收"
    else:
        hero_num, hero_unit = "5", "KG起收"

    cards = lines[:4] if len(lines) >= 3 else (lines + ["专人免费上门取件 · 不用自己扛下楼", "回收款按订单流程结算"])[:3]
    card_html = []
    card_tweens = []
    step_gap = min(1.35, max(0.85, (duration - 3.2) / max(1, len(cards))))
    for i, text in enumerate(cards):
        st = 1.45 + i * step_gap
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
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; color: {th['ink']}; background: radial-gradient(120% 70% at 50% 6%, {th['bg1']} 0%, {th['bg2']} 46%, {th['bg3']} 100%); }}
    .grid-bg {{ position: absolute; inset: -100px; background-image: linear-gradient(rgba(22,48,38,0.05) 2px, transparent 2px), linear-gradient(90deg, rgba(22,48,38,0.05) 2px, transparent 2px); background-size: 72px 72px; }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 155px 60px 230px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; }}
    .top-title {{ font-size: 72px; font-weight: 900; line-height: 1.24; text-align: center; color: {th['ink']}; white-space: pre-line; text-shadow: 0 3px 0 rgba(255,255,255,0.85); }}
    .hero-metric {{ display: flex; align-items: baseline; justify-content: center; gap: 16px; background: linear-gradient(155deg, {th['stage1']}, {th['stage2']}); border: 3px solid {th['accent']}; border-radius: 36px; padding: 26px 64px; box-shadow: 0 18px 42px rgba(22,48,38,0.10); transform: scale(0.85); opacity: 0; }}
    .hero-num {{ font-size: 132px; font-weight: 900; color: {th['accent']}; line-height: 1; }}
    .hero-unit {{ font-size: 54px; font-weight: 800; color: {th['ink']}; }}
    .pain-badge {{ font-size: 38px; font-weight: 800; color: #C92A2A; background: rgba(201,42,42,0.10); border: 2px solid rgba(201,42,42,0.35); padding: 14px 36px; border-radius: 999px; text-decoration: line-through; opacity: 0; transform: scale(0.9); }}
    .cards {{ width: 100%; display: flex; flex-direction: column; gap: 26px; }}
    .check-card {{ display: flex; align-items: center; gap: 26px; background: linear-gradient(155deg, {th['stage1']}, {th['stage2']}); border: 2px solid rgba(22,48,38,0.10); border-radius: 28px; padding: 30px 34px; box-shadow: 0 14px 32px rgba(22,48,38,0.08); opacity: 0; transform: translateX(-60px); }}
    .chk {{ width: 68px; height: 68px; border-radius: 50%; background: {th['accent']}; color: #FFF; font-size: 42px; font-weight: 900; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
    .ctext {{ font-size: 46px; font-weight: 800; line-height: 1.35; color: {th['ink']}; }}
    .question {{ font-size: 42px; font-weight: 800; color: #FFFFFF; background: rgba(22,48,38,0.88); padding: 18px 44px; border-radius: 999px; text-align: center; opacity: 0; }}
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
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".grid-bg", {{ x: 48, y: 48, duration: {duration:.2f}, ease: "none" }}, 0)
      .to(".hero-metric", {{ opacity: 1, scale: 1, duration: 0.45, ease: "back.out(1.6)" }}, 0.08)
      .to(".pain-badge", {{ opacity: 1, scale: 1, duration: 0.35, ease: "power2.out" }}, 0.75);
    {chr(10).join('    ' + line for line in card_tweens)}
    tl.to(".question", {{ opacity: 1, duration: 0.35 }}, {max(0.5, duration - 2.6):.2f});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""


def _build_kinetic_film(item: dict, duration: float, th: dict) -> str:
    title = html.escape(str(item.get("title", "旧衣服别再塞爆衣柜")).replace("\n", "\n"))
    lines = _extract_lines(item)
    question = html.escape(str(item.get("question", "专人免费上门取件 · 省心不折腾")))

    n = max(1, len(lines))
    b1 = html.escape("\n".join(lines[: max(1, n // 3)]))
    b2 = html.escape("\n".join(lines[max(1, n // 3): max(2, 2 * n // 3)]))
    b3 = html.escape("\n".join(lines[max(2, 2 * n // 3):]) or question)

    # 按目标 duration 比例调度三段切屏，支持自定义时长
    t1_out = round(duration * 0.32, 2)
    t2_in = round(t1_out + 0.20, 2)
    t2_out = round(duration * 0.64, 2)
    t3_in = round(t2_out + 0.20, 2)
    tq_in = round(min(duration - 0.6, t3_in + 0.45), 2)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <style>
{FONT_FACE_CSS}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; font-family: "YidehaiSans", sans-serif; color: {th['ink']}; background: radial-gradient(120% 70% at 50% 6%, {th['bg1']} 0%, {th['bg2']} 46%, {th['bg3']} 100%); }}
    .orb1 {{ position: absolute; width: 680px; height: 680px; border-radius: 50%; background: radial-gradient(circle, {th['accent2']}44, transparent 70%); top: 120px; left: -120px; }}
    .orb2 {{ position: absolute; width: 620px; height: 620px; border-radius: 50%; background: radial-gradient(circle, {th['accent']}28, transparent 70%); bottom: 180px; right: -100px; }}
    .stage {{ position: relative; width: 1080px; height: 1920px; padding: 170px 64px 240px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; text-align: center; }}
    .k-top {{ font-size: 74px; font-weight: 900; line-height: 1.22; color: {th['accent']}; white-space: pre-line; text-shadow: 0 3px 0 rgba(255,255,255,0.85); }}
    .k-box {{ position: relative; width: 100%; height: 860px; background: linear-gradient(155deg, {th['stage1']}, {th['stage2']}); border: 2px solid rgba(22,48,38,0.10); border-radius: 40px; box-shadow: 0 24px 60px rgba(22,48,38,0.10); display: flex; align-items: center; justify-content: center; }}
    .beat {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48px; opacity: 0; transform: scale(1.12) translateY(32px); }}
    .beat-text {{ font-size: 72px; font-weight: 900; line-height: 1.38; color: {th['ink']}; white-space: pre-line; }}
    .accent-bar {{ width: 0px; height: 14px; border-radius: 8px; background: linear-gradient(90deg, {th['accent']}, {th['accent2']}); margin-top: 34px; }}
    .k-q {{ font-size: 44px; font-weight: 800; color: #FFFFFF; background: rgba(22,48,38,0.88); padding: 18px 46px; border-radius: 999px; opacity: 0; }}
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
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.to(".orb1", {{ x: 140, y: 100, duration: {duration:.2f}, ease: "none" }}, 0)
      .to(".orb2", {{ x: -120, y: -90, duration: {duration:.2f}, ease: "none" }}, 0)
      .to(".b1", {{ opacity: 1, scale: 1, y: 0, duration: 0.36, ease: "back.out(1.4)" }}, 0.05)
      .to(".ab1", {{ width: 320, duration: 0.45, ease: "power2.out" }}, 0.25)
      .to(".b1", {{ opacity: 0, scale: 0.88, y: -32, duration: 0.28, ease: "power2.in" }}, {t1_out:.2f})
      .to(".b2", {{ opacity: 1, scale: 1, y: 0, duration: 0.36, ease: "back.out(1.4)" }}, {t2_in:.2f})
      .to(".ab2", {{ width: 360, duration: 0.45, ease: "power2.out" }}, {t2_in + 0.20:.2f})
      .to(".b2", {{ opacity: 0, scale: 0.88, y: -32, duration: 0.28, ease: "power2.in" }}, {t2_out:.2f})
      .to(".b3", {{ opacity: 1, scale: 1, y: 0, duration: 0.36, ease: "back.out(1.4)" }}, {t3_in:.2f})
      .to(".ab3", {{ width: 400, duration: 0.45, ease: "power2.out" }}, {t3_in + 0.20:.2f})
      .to(".k-q", {{ opacity: 1, duration: 0.35 }}, {tq_in:.2f});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["film"] = tl;
  </script>
</body>
</html>
"""


def build_motion_project(item: dict, proj_dir: Path, fallback_index: int = 0) -> str:
    """按样式与 5 套浅色主题轮换生成高转化动效片工程（无品牌浮条）。"""
    proj_dir.mkdir(parents=True, exist_ok=True)
    comp_dir = proj_dir / "compositions"
    comp_dir.mkdir(exist_ok=True)

    style = normalize_motion_style(item.get("motion_style"), fallback_index=fallback_index)
    th = pick_light_theme(item, fallback_index=fallback_index)
    duration = max(3.0, float(item.get("duration", 10.0)))
    title = str(item.get("title", "亿德海旧衣回收")).replace("\n", " ")

    _write_root_index(proj_dir, title, duration, th["bg2"])
    if style == "chat":
        film_html = _build_chat_film(item, duration, th)
    elif style == "checklist":
        film_html = _build_checklist_film(item, duration, th)
    else:
        film_html = _build_kinetic_film(item, duration, th)

    (comp_dir / "film.html").write_text(film_html, encoding="utf-8")
    return f"{style}/{th['name']}"
