"""R4.0 抽出的 layout 公共 helper。

4 套 layout (grid-wrap / magazine-flow / live-set / learning-report) 之前各自
实现的文本处理与绘制小工具集中到这里；为 R4 Runtime 抽象打基础。

设计原则：
- **行为严格等价**：所有 helper 必须与原 layout 内嵌实现 1:1 对应，不调整
  几何、不调整字符串格式。否则 32 张金标准会出现像素差异。
- **零 UI/服务依赖**：保持 core/ 边界，import 仅限 PIL + 标准库。
- **不修改 DrawContext**：仍走 ctx 路径，但避免 layout 重复实现。

调用约定：
- 文本处理函数（format_date_* / truncate / safe_label / result_glyph）
  是纯函数，无副作用。
- 绘制函数（draw_pill / draw_section_label / draw_text_right_aligned /
  horizontal_rule）吃 PIL ImageDraw，不直接接 ctx（保持函数式可测）。
"""
from __future__ import annotations

from typing import Optional


# ════════════════════════════════════════════════════════
#  文本处理
# ════════════════════════════════════════════════════════


def format_date_short(iso: str) -> str:
    """ISO 时间压成 'MM-DD'，失败或空 → 原样返回。

    用于：学习报告 / 时间线 / 标签 等不需要时分秒的场景。
    等价于原 learning_report._format_date 行为。
    """
    if not iso or "T" not in iso:
        return iso or ""
    date_part = iso[:10]
    return date_part[5:] if len(date_part) >= 10 else date_part


def format_date_long(iso: str) -> str:
    """ISO 时间压成 'MM-DD HH:MM'，失败或空 → 原样返回。

    用于：直播复盘 / 入场时间 / 演唱时间 等需要精度的场景。
    等价于原 live_set._format_date 行为。
    """
    if not iso or "T" not in iso:
        return iso or ""
    date_part, _, time_part = iso.partition("T")
    mm_dd = date_part[5:] if len(date_part) >= 10 else date_part
    hh_mm = time_part[:5] if len(time_part) >= 5 else time_part
    return f"{mm_dd} {hh_mm}"


def format_date_range(start: str, end: str) -> str:
    """渲染两段时间范围，用于学习报告副标题。

    等价于原 learning_report._format_date_range 行为。
    """
    if start and end:
        return f"{format_date_short(start)} → {format_date_short(end)}"
    if start:
        return f"自 {format_date_short(start)}"
    return ""


def truncate(text: str, max_w: int, d, font) -> str:
    """按像素宽度截断文本，超长追加 '…'。

    签名 (text, max_w, d, font) 跟原 learning_report._truncate 一致，
    调用点 (s, max_w, d, font) 不变。
    """
    if d.textlength(text, font=font) <= max_w:
        return text
    while len(text) > 2 and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def safe_label(song_title: str, requester_name: str, fallback: str = "（无题）") -> str:
    """拼接「歌名 · 点歌人」标签；空点歌人返回单歌名。

    空标题 → fallback。等价于原 live_set._safe 行为。
    """
    t = song_title.strip() or fallback
    r = requester_name.strip()
    return f"{t} · {r}" if r else t


# ════════════════════════════════════════════════════════
#  状态字符映射
# ════════════════════════════════════════════════════════


# 已唱/结果状态 → 字符。live-set 海报用
RESULT_GLYPH = {
    "sung": "✓",
    "skipped": "⏭",
    "cancelled": "✗",
    "postponed": "⏸",
    "unknown": "?",
    "duplicate_merged": "⊕",
}


def result_glyph(result: str) -> str:
    """未知状态返回 '·'（与原 _RESULT_GLYPH.get(..., '·') 行为一致）。"""
    return RESULT_GLYPH.get(result, "·")


# ════════════════════════════════════════════════════════
#  绘制小工具
# ════════════════════════════════════════════════════════


def draw_pill(
    d, x: int, y: int, text: str, font,
    bg_color, fg_color,
    pad_x: int = 18, height_pad: int = 4,
    radius: int = 22, height: int = 44,
) -> int:
    """画一个圆角胶囊标签，返回胶囊总宽度。

    live-set / learning-report 都用相同的「rounded_rectangle + 文字」结构。
    几何：tw = textlength + 36（左右各 18），x_padding = 18, y_padding = 4。
    等价于两 layout 中 stats 胶囊的写死几何。
    """
    tw = d.textlength(text, font=font) + 36
    d.rounded_rectangle((x, y, x + tw, y + height), radius=radius, fill=bg_color)
    d.text((x + pad_x, y + height_pad), text, font=font, fill=fg_color)
    return tw


def draw_section_label(ctx, x: int, y: int, text: str) -> int:
    """画分节标签（复用 ctx.draw_label），返回新的 y。

    几何：y + font_label.size + 56（draw_label 内部画胶囊 + 下划线 + 17px 间距）。
    4 套 layout 都用同一公式；live_set / learning_report 的 _draw_section_label
    完全一致，抽到此处。
    """
    ctx.draw_label(x, y, text)
    return y + ctx.font_label.size + 56


def draw_text_right_aligned(d, x_right: int, y: int, text: str, font, fill) -> None:
    """画一段右对齐文字（先算 width，再算 x_left = x_right - width）。

    等价于两 layout 中「d.textlength(ts) 算右移起点」的简化封装。
    """
    w = d.textlength(text, font=font)
    d.text((x_right - w, y), text, font=font, fill=fill)


def horizontal_rule(d, x0: int, x1: int, y: int, color, width: int = 2) -> None:
    """分隔线（4 套 layout 标题区/章节间分隔共用）。

    等价于 live_set.render_page 中 d.line((M, y, W-M, y), fill=st.line, width=2)。
    """
    d.line((x0, y, x1, y), fill=color, width=width)


# ════════════════════════════════════════════════════════
#  公共常量
# ════════════════════════════════════════════════════════


# 默认 fallback 文案（之前各 layout 各自硬编码）
EMPTY_TITLE_FALLBACK = "（无题）"
