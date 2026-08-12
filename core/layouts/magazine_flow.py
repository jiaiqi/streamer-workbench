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
from .ctx import LayoutContext
from .plan import LayoutAnalysis, LayoutPlan, PagePlan, SectionPlan


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


# ── 栏数模板（P2 R4 第4步）──
# 选预设 → 一键应用 columns_per_section (8 个字数分组的栏数)
# 选 "custom" → 留空让用户手动编辑 section_map
# 0 = 跟随顶级 columns 参数；正整数 = 该分组独立栏数
COLUMN_TEMPLATES: dict[str, dict[str, int | str]] = {
    "balanced": {
        "label": "均衡",
        "description": "每组统一 2 栏，常规排版",
        "values": {"一字": 2, "二字": 2, "三字": 2, "四字": 2,
                   "五字": 2, "六字": 2, "长歌名": 2, "其他": 2},
    },
    "dense": {
        "label": "密集",
        "description": "1-2 字 3 栏，3-4 字 2 栏，长歌名单栏",
        "values": {"一字": 3, "二字": 3, "三字": 2, "四字": 2,
                   "五字": 1, "六字": 1, "长歌名": 1, "其他": 1},
    },
    "spacious": {
        "label": "宽松",
        "description": "每组单栏，大字号留白",
        "values": {"一字": 1, "二字": 1, "三字": 1, "四字": 1,
                   "五字": 1, "六字": 1, "长歌名": 1, "其他": 1},
    },
    "magazine": {
        "label": "杂志",
        "description": "1-2 字密集,3-4 字双栏,长歌名单栏,适合宽幅",
        "values": {"一字": 4, "二字": 3, "三字": 2, "四字": 2,
                   "五字": 1, "六字": 1, "长歌名": 1, "其他": 1},
    },
    "custom": {
        "label": "自定义",
        "description": "在下方表格中自由编辑",
        "values": {},  # 空 → UI 暴露 section_map 让用户填
    },
}


def get_column_templates() -> list[dict]:
    """返回栏数模板列表（供 UI 渲染下拉）。

    每项: {key, label, description, values}
    """
    return [
        {"key": k, "label": t["label"], "description": t["description"], "values": t["values"]}
        for k, t in COLUMN_TEMPLATES.items()
    ]


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
    # R4 Runtime v1: 走 SongLibrary 数据通道
    supported_channels = ("song_library",)

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("columns", "栏数", "select", 2,
                      choices=[2, 3], group="布局",
                      help="双栏宽松，三栏密集"),
            ParamSpec("columns_per_section", "每分组栏数覆盖", "section_map",
                      default={"一字": 1, "二字": 3, "三字": 2,
                                "四字": 2, "五字": 1, "六字": 1, "长歌名": 1,
                                "其他": 1},
                      group="布局", section_axis="chars",
                      help="按字数分组单独指定栏数；留 0=跟随上面「栏数」"),
            ParamSpec("collapse_threshold", "稀疏合并阈值", "int", 3,
                      min=0, max=20, group="布局", step=1,
                      help="某分组歌曲数 < 此值时与下个组合并；0=不合并"),
            ParamSpec("show_date", "显示日期", "bool", True,
                      group="样式", help="刊头是否带日期"),
            ParamSpec("margin", "边距", "int", 58, min=0, max=200,
                      group="画布", unit="px", step=2),
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
            "supported_channels": list(self.supported_channels),
        }

    def analyze(self, library, ctx: "LayoutContext", axis: str = AXIS_NONE) -> LayoutAnalysis:
        """R4 Runtime v2: 统一签名 analyze(library, ctx, axis)。

        ctx.parameters 可覆盖 axis 缺省值（ctx.parameters.get("axis", axis)）。
        返回 LayoutAnalysis 反映真实分页预估。

        v1 兼容：旧调用方 (analyze(library, canvas, axis=...)) 通过适配层
        包装 ctx 即可；本签名是 v2 唯一对外契约。
        """
        from .ctx import LayoutContext
        if not isinstance(ctx, LayoutContext):
            # v1 兼容：旧调用方传的是 canvas 而非 ctx；向上包装
            from ..spec import CanvasSpec
            if isinstance(ctx, CanvasSpec):
                ctx = LayoutContext(canvas=ctx)
            else:
                raise TypeError(f"ctx 期望 LayoutContext 或 CanvasSpec，得到 {type(ctx).__name__}")
        # axis 可由 ctx.parameters 覆盖
        effective_axis = (ctx.parameters or {}).get("axis", axis) or AXIS_NONE
        result = analyze(library, axis=effective_axis, canvas=ctx.canvas)
        return LayoutAnalysis(
            page_count=result.get("page_count", 1),
            overflow=result.get("overflow", False),
            degrade_reason=result.get("degrade_reason"),
            axes_used=(effective_axis,) if effective_axis != AXIS_NONE else (),
            total_songs=len(library.mastered()) if hasattr(library, "mastered") else 0,
        )

    def categorize(self, library, axis: str = AXIS_NONE, *, parameters: dict | None = None) -> list[PageSections]:
        """分配歌曲到页。pages=auto：每页第一桶做刊头，其后每 N 首歌换页。

        P2 R4: 接受 parameters dict，应用 columns_per_section (section_map)
        和 collapse_threshold (int) 两个用户参数。
        - collapse_threshold: 歌曲数 < 阈值的桶合并到下一个非空桶
        - columns_per_section: dict[bucket_label -> cols], 0 = 用顶级 columns
        """
        params = parameters or {}
        threshold = int(params.get("collapse_threshold", 0) or 0)
        per_section_cols = params.get("columns_per_section") or {}
        if not isinstance(per_section_cols, dict):
            per_section_cols = {}

        cats = categorize_by_axis(library, axis)
        # 应用稀疏合并：把 < threshold 的桶并到下一个非空桶
        cats = _apply_collapse(cats, threshold)
        analysis = analyze(library, axis=axis, canvas=_dummy_canvas())
        per_page = analysis["per_page_max"]
        # 把所有标题按桶顺序拼成单序列，再分页
        flat: list[tuple[str, str]] = []
        for label, titles in cats:
            for t in titles:
                flat.append((label, t))
        pages: list[PageSections] = []
        for page in range(1, analysis["page_count"] + 1):
            start = (page - 1) * per_page
            end = start + per_page
            chunk = flat[start:end]
            from collections import OrderedDict
            grouped: "OrderedDict[str, list[str]]" = OrderedDict()
            for label, t in chunk:
                grouped.setdefault(label, []).append(t)
            sections = []
            for k, v in grouped.items():
                cols = per_section_cols.get(k, 0)
                sections.append({"label": k, "songs": v, "columns": cols})
            pages.append(PageSections(page=page, sections=sections))
        return pages

    def plan(self, library, ctx: LayoutContext) -> LayoutPlan:
        """R4 Runtime v2: magazine-flow 自定义 plan()。

        区别于 base 默认：
        - axis 从 ctx.parameters['axis'] 取（默认 AXIS_NONE）
        - columns_per_section / collapse_threshold 也从 ctx.parameters 取
        - SectionPlan.columns 真实反映 columns_per_section 设置
        """
        from .plan import LayoutAnalysis, PagePlan, SectionPlan
        analysis = self.analyze(library, ctx)
        # axis 优先级：ctx.parameters > 旧签名 axis
        params = dict(ctx.parameters or {})
        axis = params.get("axis", AXIS_NONE)
        # 调自己的 categorize（接 parameters）
        page_sections = self.categorize(library, axis, parameters=params)
        pages: list[PagePlan] = []
        for ps in page_sections:
            sections = tuple(
                SectionPlan(
                    label=sec["label"],
                    song_titles=tuple(sec["songs"]),
                    columns=sec.get("columns", 1) or 1,
                )
                for sec in ps.sections
            )
            pages.append(PagePlan(page=ps.page, sections=sections))
        return LayoutPlan(
            layout_id=self.id,
            layout_version="1",
            analysis=analysis,
            pages=tuple(pages),
            param_overrides=params,
        )

    def render_page(self, ctx: DrawContext, page: int, library) -> int:
        """渲染指定页。第 1 页包含刊头。

        P2 R4: section 维度由 ctx.parameters['columns_per_section'] 决定栏数;
        0 = 跟随顶级 ctx.parameters['columns'] (默认 2)。
        """
        axis = getattr(ctx, "axis", AXIS_NONE)
        params = getattr(ctx, "parameters", {}) or {}
        page_sections = self.categorize(library, axis, parameters=params)
        if not page_sections:
            return 0
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
        # 顶级栏数（section 维度为 0 时回退到这里）
        default_cols = int(params.get("columns", 2) or 2)
        # 内容（按 sections 顺序铺）
        for section in target.sections:
            section_cols = section.get("columns", 0) or 0
            cols = section_cols if section_cols > 0 else default_cols
            cols = max(1, min(cols, 5))  # 安全限制
            ctx.draw_label(spec.margin, y, section["label"])
            y += 30
            titles = section["songs"]
            if cols == 1:
                # 单栏：直接垂直铺
                for t in titles:
                    d.text((spec.margin, y), t, font=ctx.font_song, fill=ctx.style.text)
                    y += spec.row_h
                    if y >= spec.height - spec.margin:
                        break
            else:
                # 多栏：水平均分
                avail = spec.width - 2 * spec.margin
                col_w = avail // cols
                for i, t in enumerate(titles):
                    r, c = divmod(i, cols)
                    cx = spec.margin + c * col_w
                    d.text((cx, y + r * spec.row_h), t,
                           font=ctx.font_song, fill=ctx.style.text)
                    # 本节占用行数 = ceil(len/cols)
                    rows = (len(titles) + cols - 1) // cols
                    if i == len(titles) - 1:
                        y += rows * spec.row_h
                        if y >= spec.height - spec.margin:
                            break
            y += spec.sec_gap
        return y


def _apply_collapse(
    cats: list[tuple[str, list]],
    threshold: int,
) -> list[tuple[str, list]]:
    """P2 R4: 稀疏合并 — 歌曲数 < threshold 的桶并到下一个非空桶。

    例：threshold=3, cats=[(一字, 2首), (二字, 36首), (三字, 1首), (四字, 5首)]
        → [(一字+三字, 3首), (二字, 36首), (四字, 5首)]
    合并桶的 label 用 "A+B" 形式，方便 UI 标识。

    threshold=0 → 不合并（保留所有桶）。
    """
    if threshold <= 0:
        return list(cats)
    result: list[tuple[str, list]] = []
    pending_label: str | None = None
    pending_songs: list[str] = []
    for label, songs in cats:
        if len(songs) < threshold and pending_label is None:
            # 暂存到 pending，等下一个非空桶合并
            pending_label = label
            pending_songs = list(songs)
        elif pending_label is not None:
            # 与 pending 合并
            merged_label = f"{pending_label}+{label}"
            merged_songs = pending_songs + songs
            result.append((merged_label, merged_songs))
            pending_label = None
            pending_songs = []
        else:
            result.append((label, songs))
    # 末尾 pending 单独成桶（没有下一个非空桶）
    if pending_label is not None:
        result.append((pending_label, pending_songs))
    return result


def _dummy_canvas():
    class _C:
        height = 2400
        width = 1080
        margin = 58
    return _C()
