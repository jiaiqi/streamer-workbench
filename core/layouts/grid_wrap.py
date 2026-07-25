"""全行网格绕排版（grid-wrap）—— 现有 build_playlist.py 排版逻辑移植。

categorize 按分组规则（section 标记 + 字数回退）分页：
  第1页 [一字, 二字, 三字, 四字]，第2页 [五字, 六字, 长歌名/英文]
render_page 原样搬旧 compose() 的 page1/page2 主流程，保证渲染结果一致。

分组规则（2026-07-25 定案）：
- 每首歌优先看 Song.section（1-7），这是从旧脚本手工分组直接迁移的标记
  例「恋爱ing」是 5 字但旧脚本放在三字列表 → section=3
- section 未标记的歌按字数自动分组（中文按 len(title)，含英文按分类规则）
- 覆盖文件：songs.py 的 YI/ER/SAN/.../LONG_CN 列表维护 section 标记
"""
from .base import LayoutPlugin, ParamSpec, PageSections
from ..context import DrawContext


def _group(library):
    """返回按分类列表分组的歌名列表，索引 1..6 为对应字数，7 为长歌名/英文。

    分组规则（2026-07-25 定案）：
    1. 优先用 Song.section（旧脚本手工分组标记，保证与金标准一致）
    2. 未打标 → 按字数自动分组：中文按 len()、含英文字母归入 group 7
    """
    groups = {1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: []}
    for s in library.mastered():
        t = s.title.strip()
        sec = getattr(s, "section", None)
        if sec is not None and 1 <= sec <= 7:
            groups[sec].append(t)
        elif any(c.isascii() and c.isalpha() for c in t):
            groups[7].append(t)
        else:
            n = len(t)
            groups[n if n <= 6 else 7].append(t)
    return groups


class GridWrapLayout(LayoutPlugin):
    id = "grid-wrap"
    name = "全行网格绕排版"
    pages = 2
    page_capacity = 1920
    supports_avoidance = True

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("margin", "边距", "int", 58, 0, 200),
            ParamSpec("font_song", "歌名字号", "int", 36, 20, 60),
            ParamSpec("row_h", "行高", "int", 44, 30, 80),
            ParamSpec("sec_gap", "分类间距", "int", 26, 0, 80),
        ]

    def categorize(self, library) -> list[PageSections]:
        g = _group(library)
        return [
            PageSections(1, [
                {"label": "一字", "songs": g[1]},
                {"label": "二字", "songs": g[2]},
                {"label": "三字", "songs": g[3]},
                {"label": "四字", "songs": g[4]},
            ]),
            PageSections(2, [
                {"label": "五字", "songs": g[5]},
                {"label": "六字", "songs": g[6]},
                {"label": "长歌名/英文", "songs": g[7]},
            ]),
        ]

    def render_page(self, ctx: DrawContext, page: int, library) -> int:
        spec = ctx.spec
        d = ctx.draw
        st = ctx.style
        MARGIN = spec.margin
        LABEL_H = spec.label_h
        SEC_GAP = spec.sec_gap
        ROW_H = spec.row_h
        OFF = spec.content_offset
        g = _group(library)

        if page == 1:
            y = 100 + OFF
            x2 = 200
            ctx.draw_label(MARGIN, y, "一字")
            ctx.draw_label(x2, y, "二字")
            y += LABEL_H
            for r, s in enumerate(g[1]):
                d.text((MARGIN + 4, y + r * ROW_H), s, font=ctx.font_song, fill=st.text)
            ctx.draw_grid(g[2], 5, y, x2, ctx.r_at(y))
            y += 8 * ROW_H + SEC_GAP
            ctx.draw_label(MARGIN, y, "三字")
            y += LABEL_H
            san_rows = ctx.draw_grid_wrap(g[3], 6, y, MARGIN)
            y += san_rows * ROW_H + SEC_GAP
            ctx.draw_label(MARGIN, y, "四字")
            y += LABEL_H
            ctx.draw_grid_wrap(g[4], 5 if spec.avoid_zones else 6, y, MARGIN)
            return y

        # page == 2
        y = 100 + OFF
        ctx.draw_label(MARGIN, y, "五字")
        y += LABEL_H
        ctx.draw_grid_wrap(g[5], 4, y, MARGIN)
        y += 6 * ROW_H + SEC_GAP
        ctx.draw_label(MARGIN, y, "六字")
        y += LABEL_H
        ctx.draw_grid_wrap(g[6], 3, y, MARGIN)
        y += 5 * ROW_H + SEC_GAP
        ctx.draw_label(MARGIN, y, "长歌名/英文")
        y += LABEL_H

        # 英文在前，其余按短到长；左列从 MARGIN，右列右缘贴 r_at
        long = g[7]
        english = [s for s in long if any(c.isascii() and c.isalpha() for c in s)]
        cn = sorted([s for s in long if s not in english], key=len)
        short = english + [s for s in cn if len(s) <= 9]
        extra = [s for s in cn if len(s) > 9]
        half = (len(short) + 1) // 2
        left, right = short[:half], short[half:]
        lw = max((d.textlength(s, font=ctx.font_song) for s in left), default=0)
        rw = max((d.textlength(s, font=ctx.font_song) for s in right), default=0)
        rx = ctx.r_at(y) - rw
        for r, s in enumerate(left):
            d.text((MARGIN, y + r * ROW_H), s, font=ctx.font_song, fill=st.text)
        for r, s in enumerate(right):
            d.text((rx, y + r * ROW_H), s, font=ctx.font_song, fill=st.text)
        y += half * ROW_H + 12
        for s in extra:
            d.text((MARGIN, y), s, font=ctx.font_song, fill=st.text)
            y += ROW_H + 4
        return y
