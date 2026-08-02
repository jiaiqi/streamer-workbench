"""全屏柔光绕排版（fullscreen-flow）—— 蓝图 v0.1 M0.2。

设计要点（脑暴蓝图 §3.5 全屏柔光绕排歌单）：
- 默认 1080 × 2400（9:20）全屏长图
- 右侧全避让：x > 940 且 y > 1080 区域禁文（直播平台操作栏）
- 2 页字数目录：
  - 第 1 页：一字 + 二字 + 三字 + 四字（蓝图的"一字 + 二字同一横带，随后三字、四字"）
  - 第 2 页：五字 + 六字 + 长歌名/英文
- 字数分组与 grid_wrap 一致（沿用 _group 规则）
- 强制支持避让（supports_avoidance=True 默认即开）
- 与 grid-wrap 的核心区别：fullscreen-flow 强制 9:20 + 全避让，且分组顺序锁定
"""
from __future__ import annotations

from .base import LayoutPlugin, ParamSpec, PageSections
from .grid_wrap import _group
from ..context import DrawContext


# 强制使用的画布预设（蓝图中"1080×2400（9:20）全屏长图"）
REQUIRED_CANVAS = "抖音全屏 9:20"


class FullscreenFlowLayout(LayoutPlugin):
    id = "fullscreen-flow"
    name = "全屏柔光绕排版"
    pages = 2
    supports_avoidance = True
    # R4 Runtime v1: 走 SongLibrary 数据通道（与 grid-wrap 一致）
    supported_channels = ("song_library",)

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("margin", "边距", "int", 58, min=0, max=200,
                      group="画布", unit="px", step=2,
                      help="四边留白，0 表示贴边"),
            ParamSpec("font_song", "歌名字号", "int", 34, min=20, max=60,
                      group="样式", unit="pt", step=1,
                      help="歌名主体字号（全屏 9:20 略小于 grid-wrap 36）"),
            ParamSpec("row_h", "行高", "int", 44, min=30, max=80,
                      group="样式", unit="px", step=1,
                      help="每行垂直高度"),
            ParamSpec("sec_gap", "分类间距", "int", 26, min=0, max=80,
                      group="样式", unit="px", step=1,
                      help="分组标题与正文间距"),
        ]

    def supports_canvas(self, canvas_id: str) -> bool:
        """fullscreen-flow 强制 9:20 画布（蓝图中"默认 1080×2400 全屏长图"）。"""
        return canvas_id == REQUIRED_CANVAS

    def estimate_capacity(self, canvas) -> dict:
        """按 9:20 全屏画布估算每页可容纳歌曲数（与 grid-wrap 类似但留余量给全避让）。"""
        page1 = {"1": 50, "2": 50, "3": 60, "4": 50}
        page2 = {"5": 50, "6": 40, "7": 30}
        return {
            "pages": 2,
            "page_capacity": [page1, page2],
            "page_total_max": 60,
        }

    def check_overflow(
        self, library, canvas,
    ) -> tuple[bool, str]:
        """fullscreen-flow 9:20 全屏可放更多；预警阈值与 estimate_capacity 对齐。"""
        groups = _group(library)
        cap = self.estimate_capacity(canvas)
        for page_idx, page_caps in enumerate(cap["page_capacity"], start=1):
            for gid, songs in groups.items():
                page_cap = page_caps.get(str(gid))
                if page_cap is None:
                    continue
                if len(songs) > page_cap:
                    return True, (
                        f"页{page_idx} 分组{gid} 含 {len(songs)} 首, "
                        f"超出页容量 {page_cap}（画图仍能跑通, 仅为预警）"
                    )
        return False, ""

    def categorize(self, library) -> list[PageSections]:
        """字数目录：第 1 页一/二/三/四字；第 2 页五/六/长歌名。"""
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
        """全屏 9:20 渲染：与 grid_wrap 相同几何，但 OFF 偏移更大（画布 2400 vs 1920）。"""
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
            # 蓝图要求"一字 + 二字同一横带" — 同一行写两个标签
            x2 = 200
            ctx.draw_label(MARGIN, y, "一字")
            ctx.draw_label(x2, y, "二字")
            y += LABEL_H
            # 一字在左侧纵排（窄列），二字在右侧网格
            for r, s in enumerate(g[1]):
                d.text((MARGIN + 4, y + r * ROW_H), s, font=ctx.font_song, fill=st.text)
            ctx.draw_grid(g[2], 5, y, x2, ctx.r_at(y))
            y += 8 * ROW_H + SEC_GAP
            # 三字 / 四字（同 grid_wrap 第 1 页下半）
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

        # 长歌名/英文分流：英文+短长名双列，超长中文独占行
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
