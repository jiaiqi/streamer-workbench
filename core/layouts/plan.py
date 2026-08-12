"""R4 Runtime v2: LayoutPlan 数据结构 — Layout 输入与输出中间层。

设计要点（v2 草案 2026-08-12）：
- 不可变 dataclass（frozen=True），可序列化、可哈希、可缓存
- 与 RenderDocument 类似：先生成 Plan，再用 Plan 渲染
- 不引入新依赖；纯 dataclass + types
- Plan 是「layout 自报的输出意图」，engine 据此选择「画法」；
  实际像素仍由 layout.render_page() 决定（保留向后兼容）
- 与 PageSections（v1 阶段的轻量 dataclass）共存；本模块提供更丰富的
  数据结构；LayoutPlugin 默认 plan() 从 PageSections 派生

字段命名约定：
  - song_titles  — 与 PageSections.sections[].songs 一致（List[str]）
  - bbox         — 0-1 归一化坐标（与 Anchors 约定一致）
  - axes_used    — 与 magazine_flow.VALID_AXES 一致

不可变设计：
  - 所有 list 输入在 __post_init__ 转 tuple（frozen + 可哈希）
  - max_density 用 MappingProxyType 包装（不可变 dict）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, Optional, Tuple

# Section 排版策略（v2 锁定的 3 种；v3 增 Path/Orbit）
SectionLayoutKind = Literal["flow", "columns", "list"]


def _freeze_list(value: Any) -> Tuple:
    """list/tuple → tuple（frozen 友好）。"""
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise TypeError(f"期望 list/tuple，得到 {type(value).__name__}")


def _freeze_mapping(value: Any) -> Mapping:
    """dict/Mapping → 不可变 MappingProxyType（frozen 友好）。"""
    if value is None:
        return MappingProxyType({})
    if isinstance(value, Mapping):
        return MappingProxyType(dict(value))
    raise TypeError(f"期望 Mapping，得到 {type(value).__name__}")


@dataclass(frozen=True)
class SectionPlan:
    """一页里的一个分类段。

    字段：
      label            分类标签（一字/二字/已唱/待唱/...)
      song_titles      该段包含的歌曲标题列表（与 PageSections.songs 一致）
      layout_kind      排版策略（v2: flow/columns/list）
      columns          栏数（1/2/3；0 = 跟随 page 级 columns；负数 = 留待 v3）
      decoration       装饰带标识（v3 启用；v2 留 None）
      bbox             该段在画布上的预估 bbox（0-1 归一化：(x1, y1, x2, y2)；
                      可选；由 layout 估算；None = 暂无估算）
    """
    label: str
    song_titles: Tuple[str, ...]
    layout_kind: SectionLayoutKind = "flow"
    columns: int = 1
    decoration: Optional[str] = None
    bbox: Optional[Tuple[float, float, float, float]] = None

    def __post_init__(self) -> None:
        # 强制转 tuple（frozen 不可变 + 哈希友好）
        object.__setattr__(self, "song_titles", _freeze_list(self.song_titles))
        if self.bbox is not None:
            object.__setattr__(self, "bbox", _freeze_list(self.bbox))

    def __hash__(self) -> int:
        # 自定义 hash：避开 dataclass 自动 hash 链路过深问题
        return hash((
            self.label,
            self.song_titles,
            self.layout_kind,
            self.columns,
            self.decoration,
            self.bbox,
        ))


@dataclass(frozen=True)
class PagePlan:
    """一页的完整计划。

    字段：
      page             页码（1-based）
      sections         该页的分类段列表
      header           页头（刊头/标题/期号；None = 无）
      footer           页脚（页码/装饰；None = 无）
      bg_strategy      背景策略（覆盖 Skin.bg_strategy；None = 走 Skin 默认）
    """
    page: int
    sections: Tuple[SectionPlan, ...]
    header: Optional[str] = None
    footer: Optional[str] = None
    bg_strategy: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", _freeze_list(self.sections))

    def __hash__(self) -> int:
        return hash((
            self.page,
            self.sections,
            self.header,
            self.footer,
            self.bg_strategy,
        ))


@dataclass(frozen=True)
class LayoutAnalysis:
    """Layout 对输入数据的「预估分析」（不画图，只算元数据）。

    字段：
      page_count       预估页数（fixed 布局固定 2/1；auto 布局按内容算）
      overflow         是否超容量（grid-wrap 兼容用）
      degrade_reason   降级原因（"数据不足/超容量/无匹配" 等；None = 正常）
      sections_count   分类段总数（所有页加总）
      axes_used        实际使用的分类轴（v2: chars/artist/genre/...）
      total_songs      输入歌曲数
      max_density      实际密度（与 capabilities.max_density 比对；Mapping 不可变）
    """
    page_count: int
    overflow: bool = False
    degrade_reason: Optional[str] = None
    sections_count: int = 0
    axes_used: Tuple[str, ...] = ()
    total_songs: int = 0
    max_density: Mapping = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "axes_used", _freeze_list(self.axes_used))
        object.__setattr__(self, "max_density", _freeze_mapping(self.max_density))

    def __hash__(self) -> int:
        return hash((
            self.page_count,
            self.overflow,
            self.degrade_reason,
            self.sections_count,
            self.axes_used,
            self.total_songs,
            tuple(sorted(self.max_density.items())),
        ))


@dataclass(frozen=True)
class LayoutPlan:
    """Layout 对一次渲染输入的「完整输出计划」。

    字段：
      layout_id        "grid-wrap" / "magazine-flow" / ...
      layout_version   布局版本（v1 阶段固定 "1"；v2 起 layout 可自报）
      analysis         LayoutAnalysis
      pages            PagePlan 列表
      effective_palette_name  实际生效的 palette 名（v3 由 Skin 决定；v2 = theme.name）
      param_overrides  实际应用的参数覆盖（来自 Skin.param_overrides + 用户 parameters 合并；Mapping 不可变）
    """
    layout_id: str
    layout_version: str = "1"
    analysis: LayoutAnalysis = field(default_factory=lambda: LayoutAnalysis(1))
    pages: Tuple[PagePlan, ...] = ()
    effective_palette_name: str = ""
    param_overrides: Mapping = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", _freeze_list(self.pages))
        object.__setattr__(self, "param_overrides",
                           _freeze_mapping(self.param_overrides))

    def __hash__(self) -> int:
        return hash((
            self.layout_id,
            self.layout_version,
            self.analysis,
            self.pages,
            self.effective_palette_name,
            tuple(sorted(self.param_overrides.items())),
        ))


__all__ = [
    "SectionLayoutKind",
    "SectionPlan",
    "PagePlan",
    "LayoutAnalysis",
    "LayoutPlan",
]
