"""DrawContext：传给排版插件的绘图上下文。

既有「原料」（画笔、规格、颜色角色、字体），也有「公共绘制能力」
（胶囊标签、网格、绕排——从旧脚本提炼，所有排版可复用）。

draw_label / draw_grid / draw_grid_wrap 严格照抄旧实现，保证渲染结果与现状一致。
"""
from dataclasses import dataclass
from typing import List

from PIL import ImageDraw, ImageFont

from .spec import CanvasSpec
from .style import Style


@dataclass
class DrawContext:
    draw: ImageDraw.ImageDraw
    spec: CanvasSpec
    style: Style
    font_song: ImageFont.FreeTypeFont
    font_label: ImageFont.FreeTypeFont

    def draw_label(self, x, y, text):
        st = self.style
        d = self.draw
        font_label = self.font_label
        tw = d.textlength(text, font=font_label)
        pad_x, pad_y = 18, 8
        th = font_label.size + 6
        d.rounded_rectangle((x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y),
                            radius=18, fill=st.pill)
        d.text((x, y), text, font=font_label, fill=st.label)
        uy = y + th + pad_y + 4
        d.rounded_rectangle((x - 2, uy, x + tw + 2, uy + 3), radius=2, fill=st.line)

    def draw_grid(self, songs, cols, y0, x0_area, x1_area):
        """全行分布：第一列文字从 x0_area 开始，最后一列在 x1_area 结束。
        返回栏 x 坐标列表。"""
        st = self.style
        d = self.draw
        font = self.font_song
        colws = []
        for c in range(cols):
            ws = [d.textlength(s, font=font) for i, s in enumerate(songs) if i % cols == c]
            colws.append(max(ws) if ws else 0)
        gutter = max(12, (x1_area - x0_area - sum(colws)) / max(cols - 1, 1))
        positions = []
        cx = x0_area
        for wcol in colws:
            positions.append(cx)
            cx += wcol + gutter
        for i, s in enumerate(songs):
            r, c = divmod(i, cols)
            d.text((positions[c], y0 + r * self.spec.row_h), s, font=font, fill=st.text)
        return positions

    def draw_grid_wrap(self, songs, cols, y0, x0_area):
        """绕排版网格（同列减栏）。详见 歌单海报生成器-项目结构设计.md 6.2。
        返回实际占用行数。"""
        st = self.style
        d = self.draw
        spec = self.spec
        font = self.font_song
        AVOID = bool(spec.avoid_zones)
        R_BELOW = spec.r_below
        ROW_H = spec.row_h

        def R_at(y):
            if AVOID and y + 36 > 1080:
                return R_BELOW
            return spec.width - spec.margin

        rows = (len(songs) + cols - 1) // cols
        if not AVOID:
            self.draw_grid(songs, cols, y0, x0_area, R_at(y0))
            return rows
        r_cut = 0
        while r_cut < rows and y0 + r_cut * ROW_H + 36 <= 1080:
            r_cut += 1
        if r_cut == 0 or r_cut == rows:
            self.draw_grid(songs, cols, y0, x0_area, R_at(y0))
            return rows
        colws = []
        for c in range(cols):
            ws = [d.textlength(s, font=font) for i, s in enumerate(songs) if i % cols == c]
            colws.append(max(ws) if ws else 0)
        gutter = max(12, (R_at(y0) - x0_area - sum(colws)) / max(cols - 1, 1))
        positions = []
        cx = x0_area
        for wcol in colws:
            positions.append(cx)
            cx += wcol + gutter
        for i in range(r_cut * cols):
            r, c = divmod(i, cols)
            d.text((positions[c], y0 + r * ROW_H), songs[i], font=font, fill=st.text)
        k = cols
        while k > 1 and positions[k - 1] + colws[k - 1] > R_BELOW:
            k -= 1
        rest = songs[r_cut * cols:]
        yb = y0 + r_cut * ROW_H
        for i, s in enumerate(rest):
            r, c = divmod(i, k)
            d.text((positions[c], yb + r * ROW_H), s, font=font, fill=st.text)
        rows_bot = (len(rest) + k - 1) // k
        return r_cut + rows_bot
