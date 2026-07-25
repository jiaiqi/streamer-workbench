"""DrawContext：传给排版插件的绘图上下文。

既有「原料」（画笔、规格、颜色角色、字体），也有「公共绘制能力」
（胶囊标签、网格、绕排——从旧脚本提炼，所有排版可复用）。

draw_label / draw_grid / draw_grid_wrap 严格照抄旧实现，保证渲染结果与现状一致。

避让区几何定义来自 CanvasSpec.avoid_zones，但避让策略（r_at / r_below）
是 grid-wrap 的实现细节，不放在 CanvasSpec 上。
"""
from dataclasses import dataclass
from typing import List

from PIL import ImageDraw, ImageFont

from .spec import CanvasSpec
from .style import Style


# ---- grid-wrap 避让策略常量 ----
# 硬禁文边界右 x；分界线下右边界为 R_BELOW=856（右缩约一栏，硬禁文边界 940 留 84px 余量）
AVOID_CUTOFF_Y = 1080   # 分界线 y
AVOID_HARD_X = 940       # 硬禁文边界 x
R_BELOW = 856            # 分界线下右边界


def _r_at(spec: CanvasSpec, y: int) -> int:
    """grid-wrap 绕排右边界：歌名 y 在分界线上方 → 满宽，下方 → R_BELOW。"""
    if spec.avoid_zones and y + 36 > AVOID_CUTOFF_Y:
        return R_BELOW
    return spec.width - spec.margin


@dataclass
class DrawContext:
    draw: ImageDraw.ImageDraw
    spec: CanvasSpec
    style: Style
    font_song: ImageFont.FreeTypeFont
    font_label: ImageFont.FreeTypeFont

    # ---- 排版公共能力 ----

    def r_at(self, y: int) -> int:
        """绕排右边界（grid-wrap 语义），排版插件按需调用。"""
        return _r_at(self.spec, y)

    @property
    def r_below(self) -> int:
        """分界线下右边界。"""
        return R_BELOW

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
        ROW_H = spec.row_h

        rows = (len(songs) + cols - 1) // cols
        if not AVOID:
            self.draw_grid(songs, cols, y0, x0_area, _r_at(spec, y0))
            return rows
        r_cut = 0
        while r_cut < rows and y0 + r_cut * ROW_H + 36 <= AVOID_CUTOFF_Y:
            r_cut += 1
        if r_cut == 0 or r_cut == rows:
            self.draw_grid(songs, cols, y0, x0_area, _r_at(spec, y0))
            return rows
        colws = []
        for c in range(cols):
            ws = [d.textlength(s, font=font) for i, s in enumerate(songs) if i % cols == c]
            colws.append(max(ws) if ws else 0)
        gutter = max(12, (_r_at(spec, y0) - x0_area - sum(colws)) / max(cols - 1, 1))
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
