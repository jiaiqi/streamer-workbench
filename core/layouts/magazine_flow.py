"""magazine-flow 布局（R1b）—— 刊头 + 双/三栏 + pages=auto 自动分页。

设计要点（v3 §5.3-5.4 + R1b 协议）：
- 刊头占首页顶部：标题（=Poster.name）+ 期号 + 日期占位 + 副标题
- 双/三栏走 GridContext 的 wrap/grid 零件
- 6 种分类 axes 全部可配：none/chars/artist/genre/language/initial/status
- pages=auto：分类分析 (analyze) 返回 page_count + overflow + degrade_reason；
  magazine-flow 不预设页数，按歌曲数 + canvas 自适应分页
- 旧 grid-wrap 完整保留；magazine-flow 通过 plugin.id 区分

锚点：保持现有归一化 0-1 坐标约定 (见 spec.py)；margins 沿用 CANVAS_OPTIONS
"""
from __future__ import annotations

from .base import LayoutPlugin, PageSections, ParamSpec
from ..context import DrawContext


# ── 分类 axes ──
AXIS_NONE = "none"
AXIS_CHARS = "chars"
AXIS_ARTIST = "artist"
AXIS_GENRE = "genre"
AXIS_LANGUAGE = "language"
AXIS_INITIAL = "initial"
AXIS_STATUS = "status"

VALID_AXES = (
    AXIS_NONE, AXIS_CHARS, AXIS_ARTIST, AXIS_GENRE,
    AXIS_LANGUAGE, AXIS_INITIAL, AXIS_STATUS,
)


def _group_by_chars(song):
    t = song.title.strip()
    sec = getattr(song, "section", None)
    # section → label
    section_to_label = {1: "一字", 2: "二字", 3: "三字", 4: "四字",
                       5: "五字", 6: "六字", 7: "长歌名"}
    if sec is not None and 1 <= sec <= 7:
        return (section_to_label[sec], sec)
    # 未标记：按字数 + 英文字母规则
    if any(c.isascii() and c.isalpha() for c in t):
        return ("长歌名", 7)
    n = len(t)
    if n <= 0:
        return ("其他", 0)
    if n <= 6:
        return (section_to_label[n], n)
    return ("长歌名", 7)


def categorize_by_axis(library, axis: str) -> list[tuple[str, list]]:
    """按指定 axis 把 active 歌曲分成 [(label, [titles])] 列表。

    输入：library (SongLibrary-like with .active()/.mastered()) + axis
    输出：[(section_label, [song_title_str, ...]), ...] 保序
    """
    if axis == AXIS_NONE:
        titles = [s.title for s in library.mastered()]
        return [("全部", titles)]

    if axis == AXIS_CHARS:
        buckets: dict[str, list[str]] = {}
        for s in library.mastered():
            label, _sec = _group_by_chars(s)
            buckets.setdefault(label, []).append(s.title)
        # 固定顺序以保证金标准稳定
        order = ["一字", "二字", "三字", "四字", "五字", "六字", "长歌名", "其他"]
        return [(k, buckets.get(k, [])) for k in order if buckets.get(k)]

    if axis == AXIS_ARTIST:
        buckets: dict[str, list[str]] = {}
        for s in library.mastered():
            key = s.artists[0] if s.artists else "其他"
            buckets.setdefault(key, []).append(s.title)
        return [(k, v) for k, v in sorted(buckets.items())]

    if axis == AXIS_GENRE:
        buckets: dict[str, list[str]] = {}
        for s in library.mastered():
            tag = (s.tags[0] if getattr(s, "tags", []) else "未分类")
            buckets.setdefault(tag, []).append(s.title)
        return [(k, v) for k, v in sorted(buckets.items())]

    if axis == AXIS_LANGUAGE:
        buckets: dict[str, list[str]] = {}
        for s in library.mastered():
            has_ascii = any(c.isascii() and c.isalpha() for c in s.title)
            key = "英文" if has_ascii else "中文"
            buckets.setdefault(key, []).append(s.title)
        return [(k, v) for k, v in sorted(buckets.items())]

    if axis == AXIS_INITIAL:
        buckets: dict[str, list[str]] = {}
        for s in library.mastered():
            first = s.pinyin[:1].upper() if getattr(s, "pinyin", "") else "#"
            buckets.setdefault(first, []).append(s.title)
        return [(k, v) for k, v in sorted(buckets.items())]

    if axis == AXIS_STATUS:
        # 已分类轴：active / draft；P1 magazine-flow 渲染层只读 mastered()，
        # 这里仍按 status 分桶供 analysis 使用
        buckets: dict[str, list[str]] = {"已会": [], "未会": []}
        for s in library.songs if hasattr(library, "songs") else []:
            k = "已会" if getattr(s, "status", "active") == "active" else "未会"
            buckets[k].append(s.title)
        return [(k, v) for k, v in buckets.items() if v]

    # 兜底
    titles = [s.title for s in library.mastered()]
    return [("全部", titles)]


def analyze(library, *, axis: str, canvas) -> dict:
    """返回 layout 适配的真实页数 / 容量 / 溢出原因。

    协议约束：
    - pages 最小 = max(ceil(songs / per_page), 1)；上限 min_pages/max_pages
    - 单页近似容量 = max(1, canvas.height - 2 * canvas.margin - kHeadHeight) / kRowHeight
    - 该函数只做读取，不修改任何状态
    """
    categories = categorize_by_axis(library, axis)
    total = sum(len(titles) for _, titles in categories)
    # 经验值：刊头占 280px，每首歌 60px（包含间距），单页可装 ~36 首
    head_h = 280
    row_h = 60
    usable = max(1, canvas.height - 2 * canvas.margin - head_h)
    per_page = max(1, usable // row_h)
    page_count = max(1, -(-total // per_page))  # ceil(total/per_page)
    # 桶溢出（单个分组过满）
    overflow: list[str] = []
    for label, titles in categories:
        if len(titles) > per_page:
            overflow.append(f"{label}({len(titles)})> {per_page}")
    return {
        "total_songs": total,
        "categories": [{"label": k, "count": len(v)} for k, v in categories],
        "per_page_max": per_page,
        "page_count": page_count,
        "overflow": overflow,
        "degrade_reason": ("single-section-overflow" if overflow else None),
    }


class MagazineFlowLayout(LayoutPlugin):
    """R1b: 刊头 + 双/三栏 + pages=auto 自动分页布局。"""
    id = "magazine-flow"
    name = "刊头流式分页"
    pages: int | None = None  # auto: 由 analyze 决定
    supports_avoidance = True

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("columns", "栏数", "choice", 2, choices=[2, 3]),
            ParamSpec("show_date", "显示日期", "bool", True),
            ParamSpec("margin", "边距", "int", 58, 0, 200),
        ]

    def capabilities(self) -> dict:
        return {
            "supported_canvas_ids": ["9:16", "9:20", "3:4", "1:1", "A4"],
            "required_theme_capabilities": [],
            "supports_auto_pagination": True,
            "supports_manual_pages": True,
            "supports_grouping": list(VALID_AXES),
            "page_policy_mode": "auto",
            "max_density": {"per_page": 36},
        }

    def analyze(self, library, canvas, axis: str = AXIS_NONE) -> dict:
        """R1b: 暴露给 API 上层（如 /api/layouts/{id}/analyze）。

        UI 据此显示「预估 3 页」与「按歌手分桶将溢出」。
        """
        return analyze(library, axis=axis, canvas=canvas)

    def categorize(self, library, axis: str = AXIS_NONE) -> list[PageSections]:
        """分配歌曲到页。pages=auto：每页第一桶做刊头，其后每 N 首歌换页。

        R1b 简化版：均分为 N 页（每页 ~ per_page_max 首歌）。真实场景再迭代。
        """
        cats = categorize_by_axis(library, axis)
        analysis = analyze(library, axis=axis, canvas=_dummy_canvas())
        per_page = analysis["per_page_max"]
        # 把所有标题按桶顺序拼成单序列，再分页
        flat: list[tuple[str, str]] = []  # (bucket_label, title)
        for label, titles in cats:
            for t in titles:
                flat.append((label, t))
        pages: list[PageSections] = []
        for page in range(1, analysis["page_count"] + 1):
            start = (page - 1) * per_page
            end = start + per_page
            chunk = flat[start:end]
            # 同桶归类
            from collections import OrderedDict
            grouped: "OrderedDict[str, list[str]]" = OrderedDict()
            for label, t in chunk:
                grouped.setdefault(label, []).append(t)
            sections = [{"label": k, "songs": v} for k, v in grouped.items()]
            pages.append(PageSections(page=page, sections=sections))
        return pages

    def render_page(self, ctx: DrawContext, page: int, library) -> int:
        """渲染指定页。第 1 页包含刊头。"""
        axis = getattr(ctx, "axis", AXIS_NONE)
        page_sections = self.categorize(library, axis)
        if not page_sections:
            return 0
        # 取 page_th 的 sections：页码 1-based，超出返回首页或 last
        target = None
        for ps in page_sections:
            if ps.page == page:
                target = ps
                break
        if target is None:
            target = page_sections[-1]
        spec = ctx.spec
        d = ctx.draw
        OFF = spec.content_offset
        y = 0
        # 刊头
        if page == 1:
            y = 100 + OFF
            ctx.draw_label(spec.margin, y, "MAGAZINE FLOW")
            y += 60
            # 标题 + 日期（简化：用 ctx.title 替代）
            try:
                d.text((spec.margin, y), getattr(ctx, "title", "") or "Poster",
                       font=ctx.font_title, fill=ctx.style.text)
            except AttributeError:
                d.text((spec.margin, y), getattr(ctx, "title", "") or "Poster",
                       font=ctx.font_song, fill=ctx.style.text)
            y += 80
            if getattr(ctx, "subtitle", ""):
                d.text((spec.margin, y), ctx.subtitle, font=ctx.font_song,
                       fill=ctx.style.mist)
                y += 40
            y += 30
        # 内容（按 sections 顺序铺）
        for section in target.sections:
            ctx.draw_label(spec.margin, y, section["label"])
            y += 30
            col = 0
            x = spec.margin
            titles = section["songs"]
            col_w = (spec.width - 2 * spec.margin) // 2
            for t in titles:
                d.text((x, y), t, font=ctx.font_song, fill=ctx.style.text)
                y += spec.row_h
                if y >= spec.height - spec.margin:
                    break
            y += spec.sec_gap
        return y


def _dummy_canvas():
    class _C:
        height = 2400
        width = 1080
        margin = 58
    return _C()
