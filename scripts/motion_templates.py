#!/usr/bin/env python3
"""
亿德海「动效片」三套高质感 MotionFace 风格 HyperFrames / OpenMotion HTML+GSAP 母版生成器（v3.1.0）
严格遵守 knowledge/01-brand-rules.md、04-visual-style.md 与 06/09 全部硬要求，以及 HyperFrames 子合成规范：
- 必须声明 @font-face (local 中文字体)
- 顶层 index.html 拆子合成到 compositions/film.html (data-composition-src + <template> 容器)
- 全程使用 gsap.fromTo(...)，GSAP 动画元素不写 CSS 初始 transform，避免 gsap_css_transform_conflict
- 首帧 0.05s 内饱满呈现，无长淡入留白；严格遵守抖音/视频号/小红书 9:16 安全区
- 彻底移除底部品牌浮条与全屏静态尾卡，话音/信息结束即利落收尾
- 内置 5 套已验证浅色生活主题自动轮换（暖米橙 / 浅雾青 / 暖杏陶 / 浅暖金 / 淡薄荷），拒绝整批深绿发闷

三套全新内置样式（灵感来自 Motion Face 动效广场 P0 信息图解与卡片归档交互）：
1. split_compare —— 一卡拆两类｜分类对比动效（总卡一分为二：可收绿卡 vs 不收红卡 + 红线划掉，避坑科普神器）
2. pack_archive  —— 卡片自动归档｜凑齐 5kg/3件进袋动效（4 张物品卡依次飞入回收袋 + 进度条与重量实时增长，强收纳爽感）
3. ranking       —— 动态排名攀升榜｜Top 4 占窝/痛点榜单（自下而上悬念展开 + 进度条攀升 + TOP 1 高亮角标，高完播盘点利器）
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

STYLES = ("split_compare", "pack_archive", "ranking")

STYLE_ALIASES = {
    "split_compare": "split_compare",
    "compare": "split_compare",
    "split": "split_compare",
    "一卡拆两类": "split_compare",
    "分类对比": "split_compare",
    "对比": "split_compare",
    "避坑": "split_compare",
    "pack_archive": "pack_archive",
    "pack": "pack_archive",
    "archive": "pack_archive",
    "卡片归档": "pack_archive",
    "自动归类": "pack_archive",
    "打包": "pack_archive",
    "凑单": "pack_archive",
    "ranking": "ranking",
    "rank": "ranking",
    "top": "ranking",
    "排名攀升": "ranking",
    "排行榜": "ranking",
    "榜单": "ranking",
    "盘点": "ranking",
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
      src: local("PingFangSC-Semibold"), local("PingFangSC-Regular"), local("Hiragino Sans GB"), local("Microsoft YaHei"), local("SimHei");
      font-weight: 400 900;
    }
"""
FONT_STACK = '"YidehaiSans", system-ui, sans-serif'

_SVG_CHECK = (
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<polyline points="20 6 9 17 4 12"></polyline></svg>'
)

_SVG_CROSS = (
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
)

_SVG_BOX = (
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path>'
    '<line x1="3" y1="6" x2="21" y2="6"></line>'
    '<path d="M16 10a4 4 0 0 1-8 0"></path></svg>'
)

_SVG_ITEM_ICONS = [
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M20.38 3.46L16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"></path></svg>',
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17l4-9 4 4 5-6 3 11H4z"></path><line x1="4" y1="20" x2="20" y2="20"></line></svg>',
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="3"></rect><path d="M8 7V5a4 4 0 0 1 8 0v2"></path></svg>',
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"></rect><line x1="3" y1="10" x2="21" y2="10"></line><line x1="8" y1="15" x2="16" y2="15"></line></svg>',
]


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


def _clean_text(raw: Any, fallback: str = "") -> str:
    s = str(raw if raw is not None else fallback).strip()
    return s or fallback


def _write_root_index(proj_dir: Path, title: str, duration: float, bg_color: str) -> None:
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>{html.escape(title)}</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
{FONT_FACE_CSS}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: {bg_color};
      font-family: {FONT_STACK};
    }}
    #root {{
      position: relative;
      width: 100%;
      height: 100%;
      overflow: hidden;
    }}
  </style>
</head>
<body>
  <div id="root" data-composition-id="root" data-no-timeline data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
    <div id="film" data-composition-id="film" data-composition-src="compositions/film.html" data-track="main" data-track-index="1" data-start="0" data-duration="{duration:.2f}" data-width="1080" data-height="1920"></div>
  </div>
</body>
</html>"""
    (proj_dir / "index.html").write_text(index_html, encoding="utf-8")


def _wrap_subcomposition(style_css: str, inner_html: str, script_js: str, duration: float) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
</head>
<body>
  <template>
    <style>
{FONT_FACE_CSS}
      * {{ box-sizing: border-box; }}
{style_css}
    </style>
    <div id="root" data-composition-id="film" data-width="1080" data-height="1920" data-fps="30" data-duration="{duration:.2f}">
{inner_html}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
{script_js}
    </script>
  </template>
</body>
</html>
"""


def _base_stage_css(th: dict) -> str:
    return f"""      #root {{
        position: absolute;
        inset: 0;
        overflow: hidden;
        font-family: {FONT_STACK};
        color: {th['ink']};
        background: radial-gradient(125% 75% at 50% 8%, {th['bg1']} 0%, {th['bg2']} 48%, {th['bg3']} 100%);
      }}
      .dot-grid {{
        position: absolute;
        inset: 0;
        background-image: radial-gradient(rgba(22,48,38,0.09) 2px, transparent 2px);
        background-size: 40px 40px;
        opacity: 0.65;
      }}
      .orb-a {{
        position: absolute;
        width: 520px;
        height: 520px;
        border-radius: 50%;
        top: 0;
        left: 0;
        background: radial-gradient(circle, {th['accent2']}36 0%, transparent 70%);
      }}
      .orb-b {{
        position: absolute;
        width: 520px;
        height: 520px;
        border-radius: 50%;
        bottom: 120px;
        right: 0;
        background: radial-gradient(circle, {th['accent']}24 0%, transparent 70%);
      }}
      .safe-frame {{
        position: relative;
        width: 100%;
        height: 100%;
        padding: 256px 168px 420px 92px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        align-items: stretch;
      }}
      .head-block {{
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 16px;
      }}
      .eyebrow {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 10px 24px;
        border-radius: 999px;
        background: {th['ink']};
        color: #FFFFFF;
        font-size: 29px;
        font-weight: 800;
        letter-spacing: 0.5px;
      }}
      .eyebrow-dot {{
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: {th['accent2']};
        display: inline-block;
      }}
      .main-title {{
        margin: 0;
        font-size: 62px;
        font-weight: 900;
        line-height: 1.22;
        color: {th['ink']};
        white-space: pre-line;
      }}
      .takeaway-bar {{
        align-self: stretch;
        padding: 20px 28px;
        border-radius: 22px;
        background: {th['ink']};
        color: #FFFFFF;
        font-size: 33px;
        font-weight: 800;
        line-height: 1.35;
        text-align: center;
        box-shadow: 0 16px 36px rgba(22,48,38,0.16);
      }}"""


def _build_split_compare_film(item: dict, duration: float, th: dict) -> str:
    """母版 1：一卡拆两类｜分类对比动效（总卡一分为二：可收 vs 不收）。"""
    title = _clean_text(item.get("title"), "旧衣回收先分清\n这两类千万别混装")
    question = _clean_text(item.get("question"), "分清再打包 · 专人免费上门取件")
    eyebrow = _clean_text(item.get("eyebrow"), "分类避坑指南")
    master_label = _clean_text(item.get("master_label"), "家里这堆闲置衣物\n到底哪些能收？")
    yes_label = _clean_text(item.get("yes_label"), "放心打包 · 可收品类")
    no_label = _clean_text(item.get("no_label"), "千万别混 · 不收清单")

    default_yes = [
        "四季旧衣 · 羽绒服 / 厚外套",
        "成双旧鞋 · 闲置背包斜挎包",
        "床单被罩 · 棉被毛毯小玩偶",
    ]
    default_no = [
        "枕头内芯 · 校服工服定制衣",
        "严重脏污 · 发霉破损潮湿衣物",
        "电器杂物 · 废纸塑料生活垃圾",
    ]

    raw_yes = item.get("yes_items")
    raw_no = item.get("no_items")
    if isinstance(raw_yes, list) and raw_yes:
        yes_items = [str(x).strip() for x in raw_yes if str(x).strip()][:3]
    else:
        lines = _extract_lines(item)
        parsed_yes = [l for l in lines if any(k in l for k in ("可收", "能收", "支持", "羽绒", "旧衣", "旧鞋", "包包", "棉被"))]
        yes_items = parsed_yes[:3] if len(parsed_yes) >= 2 else default_yes

    if isinstance(raw_no, list) and raw_no:
        no_items = [str(x).strip() for x in raw_no if str(x).strip()][:3]
    else:
        lines = _extract_lines(item)
        parsed_no = [l for l in lines if any(k in l for k in ("不收", "不能", "别放", "枕头", "校服", "脏", "破", "湿", "发霉"))]
        no_items = parsed_no[:3] if len(parsed_no) >= 2 else default_no

    yes_rows_html = []
    no_rows_html = []
    for i, txt in enumerate(yes_items):
        yes_rows_html.append(
            f'<div class="item-row yes-row yr{i}">'
            f'<span class="ico ico-yes">{_SVG_CHECK}</span>'
            f'<span class="itxt">{html.escape(txt)}</span>'
            f'</div>'
        )
    for i, txt in enumerate(no_items):
        no_rows_html.append(
            f'<div class="item-row no-row nr{i}">'
            f'<span class="ico ico-no">{_SVG_CROSS}</span>'
            f'<span class="itxt no-txt-wrap">{html.escape(txt)}<span class="strike st{i}"></span></span>'
            f'</div>'
        )

    s = duration / 10.0
    t_split = round(2.25 * s, 2)
    t_cards = round(2.58 * s, 2)
    t_vs = round(2.82 * s, 2)
    t_q = round(min(duration - 0.8, 7.6 * s), 2)

    style_css = _base_stage_css(th) + f"""
      .arena {{
        position: relative;
        flex: 1;
        margin: 22px 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
      }}
      .master-card {{
        position: absolute;
        left: 0;
        right: 0;
        top: 24%;
        padding: 44px 32px;
        border-radius: 32px;
        background: linear-gradient(155deg, {th['stage1']}, {th['stage2']});
        border: 3px solid {th['accent']};
        box-shadow: 0 24px 56px rgba(22,48,38,0.12);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 22px;
        text-align: center;
      }}
      .master-tag {{
        padding: 8px 22px;
        border-radius: 999px;
        background: {th['accent']};
        color: #FFFFFF;
        font-size: 28px;
        font-weight: 800;
      }}
      .master-title {{
        font-size: 42px;
        font-weight: 900;
        line-height: 1.34;
        color: {th['ink']};
        white-space: pre-line;
      }}
      .split-seam {{
        width: 100%;
        height: 4px;
        border-radius: 4px;
        background: linear-gradient(90deg, #1E7E45, {th['accent']}, #C92A2A);
      }}
      .cards-stack {{
        position: relative;
        width: 100%;
        display: flex;
        flex-direction: column;
        gap: 16px;
      }}
      .split-card {{
        background: linear-gradient(160deg, {th['stage1']}, {th['stage2']});
        border-radius: 28px;
        overflow: hidden;
        box-shadow: 0 18px 44px rgba(22,48,38,0.10);
        border: 2px solid rgba(22,48,38,0.10);
      }}
      .card-head {{
        padding: 18px 26px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        color: #FFFFFF;
        font-size: 34px;
        font-weight: 900;
      }}
      .head-yes {{ background: #1B7A43; }}
      .head-no {{ background: #C92A2A; }}
      .head-badge {{
        padding: 6px 18px;
        border-radius: 999px;
        background: rgba(255,255,255,0.22);
        font-size: 28px;
        font-weight: 800;
      }}
      .card-body {{
        padding: 18px 24px 22px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }}
      .item-row {{
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 12px 16px;
        border-radius: 18px;
        background: rgba(255,255,255,0.88);
        border: 1px solid rgba(22,48,38,0.08);
      }}
      .ico {{
        width: 44px;
        height: 44px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        color: #FFFFFF;
      }}
      .ico-yes {{ background: #1B7A43; }}
      .ico-no {{ background: #C92A2A; }}
      .itxt {{
        font-size: 31px;
        font-weight: 800;
        line-height: 1.3;
        color: {th['ink']};
      }}
      .no-txt-wrap {{
        position: relative;
        display: inline-block;
        color: #6B2A2A;
      }}
      .strike {{
        position: absolute;
        left: 0;
        right: 0;
        top: 52%;
        height: 4px;
        border-radius: 2px;
        background: #C92A2A;
      }}
      .vs-pill {{
        align-self: center;
        padding: 8px 28px;
        border-radius: 999px;
        background: {th['ink']};
        color: #FFFFFF;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 28px;
        font-weight: 900;
        letter-spacing: 1px;
        box-shadow: 0 10px 24px rgba(22,48,38,0.18);
      }}"""

    inner_html = f"""      <div class="dot-grid" data-layout-ignore></div>
      <div class="orb-a" data-layout-ignore></div>
      <div class="orb-b" data-layout-ignore></div>
      <div class="safe-frame">
        <div class="head-block" data-layout-allow-safe-zone>
          <div class="eyebrow"><span class="eyebrow-dot"></span>{html.escape(eyebrow)}</div>
          <h1 class="main-title">{html.escape(title)}</h1>
        </div>
        <div class="arena" data-layout-allow-safe-zone>
          <div class="master-card">
            <div class="master-tag">先分两步 · 打包不踩坑</div>
            <div class="master-title">{html.escape(master_label)}</div>
            <div class="split-seam"></div>
          </div>
          <div class="cards-stack">
            <div class="split-card card-yes">
              <div class="card-head head-yes"><span>{html.escape(yes_label)}</span><span class="head-badge">可上门收</span></div>
              <div class="card-body">{''.join(yes_rows_html)}</div>
            </div>
            <div class="vs-pill">VS · 别混装</div>
            <div class="split-card card-no">
              <div class="card-head head-no"><span>{html.escape(no_label)}</span><span class="head-badge">请勿混入</span></div>
              <div class="card-body">{''.join(no_rows_html)}</div>
            </div>
          </div>
        </div>
        <div class="takeaway-bar" data-layout-allow-safe-zone>{html.escape(question)}</div>
      </div>"""

    row_tweens = []
    for i in range(len(yes_items)):
        st = round((2.95 + i * 0.62) * s, 2)
        row_tweens.append(
            f'tl.fromTo(".yr{i}", {{ autoAlpha: 0, x: -34 }}, {{ autoAlpha: 1, x: 0, duration: 0.36, ease: "back.out(1.4)" }}, {st:.2f});'
        )
    for i in range(len(no_items)):
        st = round((4.85 + i * 0.68) * s, 2)
        row_tweens.append(
            f'tl.fromTo(".nr{i}", {{ autoAlpha: 0, x: 34 }}, {{ autoAlpha: 1, x: 0, duration: 0.36, ease: "back.out(1.4)" }}, {st:.2f});'
        )
        row_tweens.append(
            f'tl.fromTo(".st{i}", {{ scaleX: 0, transformOrigin: "left center" }}, {{ scaleX: 1, duration: 0.28, ease: "power2.out" }}, {st + 0.28:.2f});'
        )

    script_js = f"""      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo(".orb-a", {{ x: 0, y: 0 }}, {{ x: 65, y: 45, duration: {duration:.2f}, ease: "none" }}, 0)
        .fromTo(".orb-b", {{ x: 0, y: 0 }}, {{ x: -55, y: -45, duration: {duration:.2f}, ease: "none" }}, 0)
        .fromTo(".head-block", {{ opacity: 0.92, y: 12 }}, {{ opacity: 1, y: 0, duration: 0.32, ease: "power2.out" }}, 0)
        .fromTo(".master-card", {{ autoAlpha: 1, scale: 0.96, y: 0 }}, {{ autoAlpha: 1, scale: 1, y: 0, duration: 0.45, ease: "back.out(1.4)" }}, 0.04)
        .fromTo(".split-seam", {{ scaleX: 0.25, transformOrigin: "center center" }}, {{ scaleX: 1, duration: 0.6, ease: "power2.out" }}, 0.45)
        .fromTo(".master-card", {{ autoAlpha: 1, scale: 1 }}, {{ autoAlpha: 0, scale: 0.84, duration: 0.38, ease: "power2.in", immediateRender: false }}, {t_split:.2f})
        .fromTo(".card-yes", {{ autoAlpha: 0, y: 70, scale: 0.94 }}, {{ autoAlpha: 1, y: 0, scale: 1, duration: 0.48, ease: "back.out(1.3)" }}, {t_cards:.2f})
        .fromTo(".card-no", {{ autoAlpha: 0, y: -70, scale: 0.94 }}, {{ autoAlpha: 1, y: 0, scale: 1, duration: 0.48, ease: "back.out(1.3)" }}, {t_cards:.2f})
        .fromTo(".vs-pill", {{ autoAlpha: 0, scale: 0.4 }}, {{ autoAlpha: 1, scale: 1, duration: 0.36, ease: "back.out(1.8)" }}, {t_vs:.2f});
      {chr(10).join('      ' + line for line in row_tweens)}
      tl.fromTo(".takeaway-bar", {{ autoAlpha: 0, y: 26 }}, {{ autoAlpha: 1, y: 0, duration: 0.40, ease: "power2.out" }}, {t_q:.2f});
      window.__timelines["film"] = tl;"""

    return _wrap_subcomposition(style_css, inner_html, script_js, duration)


def _build_pack_archive_film(item: dict, duration: float, th: dict) -> str:
    """母版 2：卡片自动归档｜4 张衣物卡片依次飞入回收袋 + 进度条与重量同步增长。"""
    title = _clean_text(item.get("title"), "衣柜旧物装一袋\n轻松凑够起收标准")
    question = _clean_text(item.get("question"), "装满一袋就能约 · 专人免费上门")
    eyebrow = _clean_text(item.get("eyebrow"), "凑单打包指南")

    joined = title + "".join(_extract_lines(item))
    is_down = ("羽绒服" in joined and ("3件" in joined or "3 件" in joined))
    unit = "件" if is_down else "kg"
    target_val = 3.0 if is_down else 5.0
    target_text = "3 件起收" if is_down else "5.0 kg 起收"

    raw_pack = item.get("pack_items")
    if isinstance(raw_pack, list) and raw_pack:
        pack_items = []
        for idx, entry in enumerate(raw_pack[:4]):
            if isinstance(entry, dict):
                pack_items.append({
                    "name": _clean_text(entry.get("name"), f"闲置衣物{idx + 1}"),
                    "val": float(entry.get("weight", entry.get("count", 1.5))),
                    "tag": _clean_text(entry.get("tag"), "可回收"),
                })
            else:
                pack_items.append({"name": str(entry), "val": 1.5, "tag": "可回收"})
    elif is_down:
        pack_items = [
            {"name": "长款旧羽绒服", "val": 1.0, "tag": "占衣柜"},
            {"name": "短款羽绒外套", "val": 1.0, "tag": "闲置品"},
            {"name": "轻薄旧羽绒服", "val": 1.0, "tag": "可起收"},
            {"name": "顺带旧围巾毛衣", "val": 1.0, "tag": "加量省心"},
        ]
    else:
        lines = _extract_lines(item)
        if len(lines) >= 4:
            pack_items = [
                {"name": lines[0][:12], "val": 1.8, "tag": "第一袋"},
                {"name": lines[1][:12], "val": 1.4, "tag": "凑分量"},
                {"name": lines[2][:12], "val": 1.2, "tag": "一起装"},
                {"name": lines[3][:12], "val": 1.2, "tag": "超轻松"},
            ]
        else:
            pack_items = [
                {"name": "旧棉服 / 外套", "val": 1.8, "tag": "厚重件"},
                {"name": "起球厚毛衣", "val": 1.4, "tag": "占地方"},
                {"name": "闲置旧鞋旧包", "val": 1.2, "tag": "也能收"},
                {"name": "旧床单四件套", "val": 1.2, "tag": "轻松凑够"},
            ]

    while len(pack_items) < 4:
        pack_items.append({"name": "四季换洗旧衣", "val": 1.3, "tag": "可混装"})

    tray_html = []
    chip_html = []
    total_vals = [0.0]
    for i, pk in enumerate(pack_items):
        val_txt = f"+{pk['val']:.0f} {unit}" if unit == "件" else f"+{pk['val']:.1f} {unit}"
        ico = _SVG_ITEM_ICONS[i % len(_SVG_ITEM_ICONS)]
        tray_html.append(
            f'<div class="tray-card tc{i}">'
            f'<div class="tc-top"><span class="tc-ico tci{i}">{ico}</span>'
            f'<span class="tc-badges"><span class="tc-val tcv{i}">{val_txt}</span><span class="tc-done tcd{i}">✓ 已入袋</span></span></div>'
            f'<div class="tc-name">{html.escape(pk["name"])}</div>'
            f'<div class="tc-tag">{html.escape(pk["tag"])}</div>'
            f'</div>'
        )
        chip_html.append(f'<span class="packed-chip pc{i}">{html.escape(pk["name"])}</span>')
        total_vals.append(round(total_vals[-1] + pk["val"], 2))

    s = duration / 10.0
    style_css = _base_stage_css(th) + f"""
      .tray-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 18px;
        margin-top: 18px;
      }}
      .tray-card {{
        padding: 22px 20px;
        border-radius: 26px;
        background: linear-gradient(155deg, {th['stage1']}, {th['stage2']});
        border: 2px solid rgba(22,48,38,0.10);
        box-shadow: 0 14px 32px rgba(22,48,38,0.08);
        display: flex;
        flex-direction: column;
        gap: 10px;
      }}
      .tc-top {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }}
      .tc-ico {{
        width: 56px;
        height: 56px;
        border-radius: 16px;
        background: {th['bg2']};
        color: {th['accent']};
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }}
      .tc-badges {{
        position: relative;
        height: 44px;
        min-width: 162px;
        display: flex;
        align-items: center;
        justify-content: flex-end;
      }}
      .tc-val, .tc-done {{
        position: absolute;
        right: 0;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 28px;
        font-weight: 900;
        white-space: nowrap;
      }}
      .tc-val {{
        background: {th['accent']}1E;
        color: {th['accent']};
      }}
      .tc-done {{
        background: #1B7A43;
        color: #FFFFFF;
      }}
      .tc-name {{
        font-size: 32px;
        font-weight: 900;
        color: {th['ink']};
        line-height: 1.25;
      }}
      .tc-tag {{
        font-size: 29px;
        font-weight: 700;
        color: {th['tag']};
      }}
      .bag-stage {{
        margin-top: 22px;
        padding: 26px 28px;
        border-radius: 32px;
        background: linear-gradient(160deg, {th['stage1']}, {th['stage2']});
        border: 3px solid {th['accent']};
        box-shadow: 0 22px 48px rgba(22,48,38,0.12);
        display: flex;
        flex-direction: column;
        gap: 16px;
      }}
      .bag-head {{
        display: flex;
        align-items: center;
        justify-content: space-between;
      }}
      .bag-title-wrap {{
        display: flex;
        align-items: center;
        gap: 14px;
      }}
      .bag-icon {{
        width: 58px;
        height: 58px;
        border-radius: 18px;
        background: {th['accent']};
        color: #FFFFFF;
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      .bag-title {{
        font-size: 34px;
        font-weight: 900;
        color: {th['ink']};
      }}
      .bag-sub {{
        font-size: 28px;
        font-weight: 700;
        color: {th['tag']};
      }}
      .bag-meter {{
        text-align: right;
      }}
      .meter-num {{
        font-size: 44px;
        font-weight: 900;
        color: {th['accent']};
        line-height: 1;
      }}
      .meter-target {{
        font-size: 28px;
        font-weight: 800;
        color: {th['tag']};
        margin-top: 4px;
      }}
      .progress-track {{
        width: 100%;
        height: 22px;
        border-radius: 999px;
        background: rgba(22,48,38,0.10);
        overflow: hidden;
      }}
      .progress-fill {{
        width: 100%;
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, {th['accent2']}, {th['accent']});
      }}
      .packed-shelf {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        min-height: 44px;
      }}
      .packed-chip {{
        padding: 8px 16px;
        border-radius: 999px;
        background: {th['ink']};
        color: #FFFFFF;
        font-size: 28px;
        font-weight: 800;
      }}
      .ready-stamp {{
        padding: 12px 20px;
        border-radius: 16px;
        background: #1B7A43;
        color: #FFFFFF;
        font-size: 29px;
        font-weight: 900;
        text-align: center;
      }}"""

    inner_html = f"""      <div class="dot-grid" data-layout-ignore></div>
      <div class="orb-a" data-layout-ignore></div>
      <div class="orb-b" data-layout-ignore></div>
      <div class="safe-frame">
        <div class="head-block" data-layout-allow-safe-zone>
          <div class="eyebrow"><span class="eyebrow-dot"></span>{html.escape(eyebrow)}</div>
          <h1 class="main-title">{html.escape(title)}</h1>
        </div>
        <div class="tray-grid" data-layout-allow-safe-zone>
          {''.join(tray_html)}
        </div>
        <div class="bag-stage" data-layout-allow-safe-zone>
          <div class="bag-head">
            <div class="bag-title-wrap">
              <div class="bag-icon">{_SVG_BOX}</div>
              <div>
                <div class="bag-title">亿德海回收袋</div>
                <div class="bag-sub">四季衣物 · 鞋包家纺都能混装</div>
              </div>
            </div>
            <div class="bag-meter">
              <div class="meter-num" id="meterReadout">0.0 {unit}</div>
              <div class="meter-target">目标：{target_text}</div>
            </div>
          </div>
          <div class="progress-track"><div class="progress-fill"></div></div>
          <div class="packed-shelf">{''.join(chip_html)}</div>
          <div class="ready-stamp">已达起收门槛 · 可直接预约免费上门</div>
        </div>
        <div class="takeaway-bar" data-layout-allow-safe-zone>{html.escape(question)}</div>
      </div>"""

    pack_tweens = []
    for i in range(4):
        t_drop = round((1.05 + i * 1.12) * s, 2)
        prev_ratio = min(1.0, total_vals[i] / target_val)
        next_ratio = min(1.0, total_vals[i + 1] / target_val)
        prev_w = total_vals[i]
        next_w = total_vals[i + 1]
        fmt_js = 'Math.round(meterState.v) + " 件"' if unit == "件" else 'meterState.v.toFixed(1) + " kg"'

        pack_tweens.append(
            f'tl.fromTo(".tc{i}", {{ scale: 1, y: 0 }}, {{ scale: 1.04, y: -6, borderColor: "{th["accent"]}", duration: 0.24, ease: "power2.out", immediateRender: false }}, {t_drop:.2f})'
            f'\n        .fromTo(".tc{i}", {{ scale: 1.04, y: -6 }}, {{ scale: 0.98, y: 0, borderColor: "#1B7A43", duration: 0.28, ease: "power2.inOut", immediateRender: false }}, {t_drop + 0.26:.2f})'
            f'\n        .fromTo(".tcv{i}", {{ autoAlpha: 1, scale: 1 }}, {{ autoAlpha: 0, scale: 0.75, duration: 0.18, ease: "power1.in", immediateRender: false }}, {t_drop + 0.20:.2f})'
            f'\n        .fromTo(".tcd{i}", {{ autoAlpha: 0, scale: 0.6 }}, {{ autoAlpha: 1, scale: 1, duration: 0.26, ease: "back.out(1.7)" }}, {t_drop + 0.40:.2f})'
            f'\n        .fromTo(".tci{i}", {{ backgroundColor: "{th["bg2"]}", color: "{th["accent"]}" }}, {{ backgroundColor: "#E4F4EA", color: "#1B7A43", duration: 0.26, immediateRender: false }}, {t_drop + 0.28:.2f})'
            f'\n        .fromTo(".pc{i}", {{ autoAlpha: 0, scale: 0.5 }}, {{ autoAlpha: 1, scale: 1, duration: 0.32, ease: "back.out(1.7)" }}, {t_drop + 0.32:.2f})'
            f'\n        .fromTo(".bag-stage", {{ scaleY: 0.97, scaleX: 1.02 }}, {{ scaleY: 1, scaleX: 1, duration: 0.34, ease: "elastic.out(1, 0.5)", immediateRender: false }}, {t_drop + 0.34:.2f})'
            f'\n        .fromTo(".progress-fill", {{ scaleX: {prev_ratio:.3f}, transformOrigin: "left center" }}, {{ scaleX: {next_ratio:.3f}, duration: 0.42, ease: "power2.out", immediateRender: false }}, {t_drop + 0.30:.2f})'
            f'\n        .fromTo(meterState, {{ v: {prev_w:.2f} }}, {{ v: {next_w:.2f}, duration: 0.42, ease: "power1.out", immediateRender: false, onUpdate: () => {{ readoutEl.textContent = {fmt_js}; }} }}, {t_drop + 0.30:.2f});'
        )

    t_stamp = round(5.65 * s, 2)
    t_q = round(min(duration - 0.8, 7.0 * s), 2)

    script_js = f"""      const readoutEl = document.getElementById("meterReadout");
      const meterState = {{ v: 0 }};
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo(".orb-a", {{ x: 0, y: 0 }}, {{ x: 65, y: 45, duration: {duration:.2f}, ease: "none" }}, 0)
        .fromTo(".orb-b", {{ x: 0, y: 0 }}, {{ x: -55, y: -45, duration: {duration:.2f}, ease: "none" }}, 0)
        .fromTo(".tray-card", {{ opacity: 0.88, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.35, stagger: 0.06, ease: "power2.out" }}, 0)
        .fromTo(".progress-fill", {{ scaleX: 0, transformOrigin: "left center" }}, {{ scaleX: 0.02, duration: 0.25 }}, 0);
      {chr(10).join('      ' + line for line in pack_tweens)}
      tl.fromTo(".ready-stamp", {{ autoAlpha: 0, scale: 0.86 }}, {{ autoAlpha: 1, scale: 1, duration: 0.42, ease: "back.out(1.7)" }}, {t_stamp:.2f})
        .fromTo(".takeaway-bar", {{ autoAlpha: 0, y: 24 }}, {{ autoAlpha: 1, y: 0, duration: 0.38, ease: "power2.out" }}, {t_q:.2f});
      window.__timelines["film"] = tl;"""

    return _wrap_subcomposition(style_css, inner_html, script_js, duration)


def _build_ranking_film(item: dict, duration: float, th: dict) -> str:
    """母版 3：动态排名攀升榜｜Top 4 自下而上悬念展开 + 进度条攀升 + TOP 1 高亮。"""
    title = _clean_text(item.get("title"), "衣柜最占空间的旧物\n你家占了几样？")
    question = _clean_text(item.get("question"), "腾空衣柜省空间 · 满 5kg 免费上门")
    eyebrow = _clean_text(item.get("eyebrow"), "居家断舍离排行榜")
    highlight_tip = _clean_text(item.get("highlight_tip"), "第 1 名最占空间：3 件羽绒服就能直接约上门！")

    default_ranks = [
        {"name": "压箱底旧羽绒服", "sub": "体积超大 · 3 件即可独立起收", "score": 96},
        {"name": "起球变形厚毛衣", "sub": "穿过两季就闲置 · 叠放最占抽屉", "score": 87},
        {"name": "磨脚闲置旧运动鞋", "sub": "鞋柜塞爆元凶 · 成双干净都能收", "score": 76},
        {"name": "落灰过时旧包包", "sub": "挂着占位置 · 换季一起打包省事", "score": 64},
    ]

    raw_ranks = item.get("ranking_items")
    if isinstance(raw_ranks, list) and raw_ranks:
        rank_items = []
        for idx, entry in enumerate(raw_ranks[:4]):
            if isinstance(entry, dict):
                rank_items.append({
                    "name": _clean_text(entry.get("name"), f"上榜旧物 {idx + 1}"),
                    "sub": _clean_text(entry.get("sub"), "闲置占地方 · 适合优先清理"),
                    "score": max(35, min(100, int(entry.get("score", 95 - idx * 10)))),
                })
            else:
                rank_items.append({"name": str(entry), "sub": "闲置占地方 · 适合优先清理", "score": 95 - idx * 10})
    else:
        lines = _extract_lines(item)
        if len(lines) >= 4:
            rank_items = [
                {"name": lines[i][:14], "sub": "换季优先清理 · 一袋打包带走", "score": 96 - i * 10}
                for i in range(4)
            ]
        else:
            rank_items = default_ranks

    while len(rank_items) < 4:
        rank_items.append(default_ranks[len(rank_items)])

    rows_html = []
    for i, rk in enumerate(rank_items):
        num = i + 1
        top_badge = '<span class="top1-badge">最优先清理</span>' if num == 1 else ""
        rows_html.append(
            f'<div class="rank-row rr{i} {"is-top1" if num == 1 else ""}">'
            f'  <div class="rank-top">'
            f'    <div class="rank-left">'
            f'      <span class="rank-num {"num-top1" if num == 1 else ""}">0{num}</span>'
            f'      <div><div class="rank-name">{html.escape(rk["name"])}{top_badge}</div>'
            f'      <div class="rank-sub">{html.escape(rk["sub"])}</div></div>'
            f'    </div>'
            f'    <div class="rank-score">{rk["score"]}%</div>'
            f'  </div>'
            f'  <div class="bar-track"><div class="bar-fill bf{i}" style="width: {rk["score"]}%"></div></div>'
            f'</div>'
        )

    s = duration / 10.0
    t_tip = round(4.85 * s, 2)
    t_q = round(min(duration - 0.8, 6.6 * s), 2)

    style_css = _base_stage_css(th) + f"""
      .title-rule {{
        width: 180px;
        height: 8px;
        border-radius: 999px;
        background: linear-gradient(90deg, {th['accent']}, {th['accent2']});
      }}
      .board-card {{
        margin: 12px 0 8px;
        padding: 22px 22px;
        border-radius: 32px;
        background: linear-gradient(160deg, {th['stage1']}, {th['stage2']});
        border: 2px solid rgba(22,48,38,0.10);
        box-shadow: 0 22px 52px rgba(22,48,38,0.10);
        display: flex;
        flex-direction: column;
        gap: 16px;
      }}
      .rank-row {{
        padding: 20px 22px;
        border-radius: 22px;
        background: rgba(255,255,255,0.92);
        border: 2px solid rgba(22,48,38,0.08);
        display: flex;
        flex-direction: column;
        gap: 14px;
      }}
      .is-top1 {{
        border-color: {th['accent']};
        background: #FFFFFF;
        box-shadow: 0 12px 28px {th['accent']}22;
      }}
      .rank-top {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }}
      .rank-left {{
        display: flex;
        align-items: center;
        gap: 16px;
        min-width: 0;
      }}
      .rank-num {{
        width: 54px;
        height: 54px;
        border-radius: 16px;
        background: {th['bg2']};
        color: {th['ink']};
        font-size: 28px;
        font-weight: 900;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }}
      .num-top1 {{
        background: {th['accent']};
        color: #FFFFFF;
      }}
      .rank-name {{
        font-size: 32px;
        font-weight: 900;
        color: {th['ink']};
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
      }}
      .top1-badge {{
        padding: 4px 12px;
        border-radius: 999px;
        background: {th['accent']};
        color: #FFFFFF;
        font-size: 28px;
        font-weight: 800;
      }}
      .rank-sub {{
        font-size: 28px;
        font-weight: 700;
        color: {th['tag']};
        margin-top: 4px;
      }}
      .rank-score {{
        font-size: 36px;
        font-weight: 900;
        color: {th['accent']};
        flex-shrink: 0;
      }}
      .bar-track {{
        width: 100%;
        height: 14px;
        border-radius: 999px;
        background: rgba(22,48,38,0.09);
        overflow: hidden;
      }}
      .bar-fill {{
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, {th['accent2']}, {th['accent']});
      }}
      .tip-banner {{
        padding: 15px 24px;
        border-radius: 20px;
        background: {th['stage1']};
        color: {th['ink']};
        border: 2px solid {th['accent']};
        font-size: 29px;
        font-weight: 900;
        text-align: center;
      }}"""

    inner_html = f"""      <div class="dot-grid" data-layout-ignore></div>
      <div class="orb-a" data-layout-ignore></div>
      <div class="orb-b" data-layout-ignore></div>
      <div class="safe-frame">
        <div class="head-block" data-layout-allow-safe-zone>
          <div class="eyebrow"><span class="eyebrow-dot"></span>{html.escape(eyebrow)}</div>
          <h1 class="main-title">{html.escape(title)}</h1>
          <div class="title-rule"></div>
        </div>
        <div class="board-card" data-layout-allow-safe-zone>
          {''.join(rows_html)}
        </div>
        <div class="tip-banner" data-layout-allow-safe-zone>{html.escape(highlight_tip)}</div>
        <div class="takeaway-bar" data-layout-allow-safe-zone>{html.escape(question)}</div>
      </div>"""

    # 自下而上悬念展开（04 -> 03 -> 02 -> 01）
    cascade_tweens = []
    order = [3, 2, 1, 0]
    for step_idx, row_idx in enumerate(order):
        t_row = round((0.15 + step_idx * 0.95) * s, 2)
        cascade_tweens.append(
            f'tl.fromTo(".rr{row_idx}", {{ autoAlpha: 0, y: 28 }}, {{ autoAlpha: 1, y: 0, duration: 0.40, ease: "back.out(1.3)" }}, {t_row:.2f})'
            f'\n        .fromTo(".bf{row_idx}", {{ scaleX: 0, transformOrigin: "left center" }}, {{ scaleX: 1, duration: 0.54, ease: "power2.out" }}, {t_row + 0.14:.2f});'
        )

    script_js = f"""      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo(".orb-a", {{ x: 0, y: 0 }}, {{ x: 65, y: 45, duration: {duration:.2f}, ease: "none" }}, 0)
        .fromTo(".orb-b", {{ x: 0, y: 0 }}, {{ x: -55, y: -45, duration: {duration:.2f}, ease: "none" }}, 0)
        .fromTo(".title-rule", {{ scaleX: 0.2, transformOrigin: "left center" }}, {{ scaleX: 1, duration: 0.5, ease: "power2.out" }}, 0.05)
        .fromTo(".board-card", {{ opacity: 0.94, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }}, 0);
      {chr(10).join('      ' + line for line in cascade_tweens)}
      tl.fromTo(".top1-badge", {{ autoAlpha: 0, scale: 0.4 }}, {{ autoAlpha: 1, scale: 1, duration: 0.36, ease: "back.out(1.8)" }}, {round(3.75 * s, 2):.2f})
        .fromTo(".tip-banner", {{ autoAlpha: 0, scale: 0.92 }}, {{ autoAlpha: 1, scale: 1, duration: 0.40, ease: "back.out(1.5)" }}, {t_tip:.2f})
        .fromTo(".takeaway-bar", {{ autoAlpha: 0, y: 24 }}, {{ autoAlpha: 1, y: 0, duration: 0.38, ease: "power2.out" }}, {t_q:.2f});
      window.__timelines["film"] = tl;"""

    return _wrap_subcomposition(style_css, inner_html, script_js, duration)


def build_motion_project(item: dict, proj_dir: Path, fallback_index: int = 0) -> str:
    """按样式与 5 套浅色主题轮换生成高质感 MotionFace 风格动效片工程（无品牌浮条）。"""
    proj_dir.mkdir(parents=True, exist_ok=True)
    comp_dir = proj_dir / "compositions"
    comp_dir.mkdir(exist_ok=True)

    style = normalize_motion_style(item.get("motion_style"), fallback_index=fallback_index)
    th = pick_light_theme(item, fallback_index=fallback_index)
    duration = max(3.0, float(item.get("duration", 10.0)))
    title = str(item.get("title", "亿德海旧衣回收")).replace("\n", " ")

    _write_root_index(proj_dir, title, duration, th["bg2"])
    if style == "split_compare":
        film_html = _build_split_compare_film(item, duration, th)
    elif style == "pack_archive":
        film_html = _build_pack_archive_film(item, duration, th)
    else:
        film_html = _build_ranking_film(item, duration, th)

    (comp_dir / "film.html").write_text(film_html, encoding="utf-8")
    return f"{style}/{th['name']}"
