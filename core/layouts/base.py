"""排版插件基类 + 参数描述。

每个排版一个模块。现有「全行网格绕排版」(grid-wrap) 是原 build_playlist.py
排版逻辑移植，作为第一个插件。新排版（便签拼贴/歌手分区…）写的时候，
胶囊标签、网格、绕排这些「零件」从 DrawContext 开箱即用，只写布局差异。

P2 R4 通用化：ParamSpec 升级为全平台契约，UI 右侧 Inspector 通用渲染。
新支持的 kind:
  - "int" / "float"   数值（带 min/max/step）
  - "bool"            开关
  - "select"          单选下拉（choices 是 list[str|int|float]）
  - "section_map"     分类→数值映射（专为「每个字数分组的栏数」设计）
  - "group_order"     分类顺序（UI 渲染成上下拖拽列表）

R4 Runtime v1：LayoutPlugin 显式声明 supported_channels（见 channel.py）。
新 layout 必须从 ("song_library" / "live_session" / "learning_report") 中
至少选一个；不声明 = 默认空 tuple = 不被任何通道接受（防御性兜底）。

R4 Runtime v2：统一 analyze(library, ctx: LayoutContext) -> LayoutAnalysis
签名（替代旧 analyze(library, canvas, **kwargs)）。LayoutPlugin 基类给默认
实现：返 LayoutAnalysis(page_count=plugin.pages or 1)，子类可 override。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, List, Literal, Optional

from .channel import DataChannel
from .ctx import LayoutContext
from .plan import LayoutAnalysis, LayoutPlan, PagePlan, SectionPlan


# UI 渲染侧的 kind 枚举（Literal 比 string 更利于前端类型生成）
ParamSpecKind = Literal[
    "int", "float", "bool", "select", "section_map", "group_order",
]


@dataclass
class ParamSpec:
    """暴露给右侧参数面板的可调项，UI 据此动态生成控件。

    字段语义：
      key           参数名（POST /api/render/document 的 parameters 字段）
      label         显示名（中文/任意）
      kind          控件类型（见 ParamSpecKind）
      default       默认值
      min / max     数值范围（kind=int/float）
      step          滑块步长（缺省=1）
      choices       kind=select 时的候选项（值列表，UI 渲染为下拉）
      group         Inspector 内的分组（"布局"/"样式"/"分组"/"画布"等）
      help          鼠标悬停提示文案
      section_axis  kind=section_map 时绑定的分组轴
                    ("chars"/"artist"/"genre"/"language"/"initial"/"status")
      unit          显示单位（如 "px"），仅展示用
    """
    key: str
    label: str
    kind: ParamSpecKind
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[list] = None
    group: str = "布局"
    help: str = ""
    section_axis: Optional[str] = None
    unit: str = ""


@dataclass
class PageSections:
    """一页的内容清单：若干分类段，每段一个标签 + 一组歌名。"""
    page: int
    sections: List[dict]   # 每项为 {"label": str, "songs": List[str]}


class LayoutPlugin(ABC):
    id: str                              # "grid-wrap"
    name: str                            # "全行网格绕排版"
    pages: int | None = None             # 固定页数（如 2）；None = 自动分页
    supports_avoidance: bool = True      # 是否支持 avoid_zones 避让
    # R4 Runtime v1：该 layout 接受哪些数据通道。子 layout 必须显式覆盖；
    # 默认空 tuple 表示"未声明"——外部按 channel 找 layout 时会被过滤掉。
    # 不强制子类必须非空（保留向后兼容：老 layout 没声明时仍能工作，
    # 显式声明后会出现在 get_layout(channel=...) 列表里）。
    supported_channels: ClassVar[tuple[DataChannel, ...]] = ()

    def get_page_capacity(self, spec) -> int:
        """单页最大内容高度（px），自动分页时使用。默认从画布高度推算。
        
        子类可覆盖以声明比默认更小/更大的页容量。
        """
        return max(1, spec.height - spec.margin * 2)

    @abstractmethod
    def params(self) -> List[ParamSpec]: ...

    @abstractmethod
    def categorize(self, library) -> List[PageSections]:
        """分页 + 每页的分类清单。"""

    @abstractmethod
    def render_page(self, ctx, page: int, library) -> int:
        """把该页内容画到 ctx 画布上。返回内容结束 y（供质检/柔光校验）。"""

    # ---- R4 Runtime v2: analyze / plan 三段式契约 ----
    def analyze(self, library, ctx: LayoutContext) -> LayoutAnalysis:
        """v2 统一签名：分析输入数据，返回 LayoutAnalysis。

        默认实现：返 LayoutAnalysis(page_count=self.pages or 1)。
        子类应 override 以反映"auto 分页"等真实分析。

        v1 兼容：旧 layout 用 analyze(library, canvas, **kwargs) 旧签名；
        仍可工作（v2 不删除旧签名，子类自己重写 v2 签名）。
        """
        fixed_pages = self.pages or 1
        return LayoutAnalysis(page_count=fixed_pages)

    def plan(self, library, ctx: LayoutContext) -> LayoutPlan:
        """v2: 生成 LayoutPlan（完整输出计划）。

        默认实现：调 analyze() + categorize()（旧签名，只传 library） +
        简单组装为 LayoutPlan。子类可 override 以处理 parameters 或
        提供更精确的 PagePlan（如 magazine-flow 的 axis/columns_per_section）。

        v1 兼容：categorize() 旧签名只接 library（不接 parameters）；
        默认 plan() 不传 parameters，magazine-flow 自己 override plan()。
        """
        analysis = self.analyze(library, ctx)
        sections = self.categorize(library)  # 旧签名
        pages: List[PagePlan] = []
        for ps in sections:
            page_plan = PagePlan(
                page=ps.page,
                sections=tuple(
                    SectionPlan(label=sec["label"], song_titles=tuple(sec["songs"]))
                    for sec in ps.sections
                ),
            )
            pages.append(page_plan)
        # 应用 param_overrides
        overrides = dict(ctx.parameters) if ctx.parameters else {}
        return LayoutPlan(
            layout_id=self.id,
            layout_version="1",
            analysis=analysis,
            pages=tuple(pages),
            param_overrides=overrides,
        )

    # ---- 额外颜色角色 ----
    # 排版可声明自己需要的扩展颜色（如卡片背景、装饰色）。
    # 子类重写此方法返回角色名列表；theme.json 可选的 extra 字段提供对应值；
    # 未提供则回退到内置默认色。
    def extra_colors(self) -> dict:
        return {}

    # ---- R4 Runtime v2: 能力矩阵 ----
    def compatible_themes(self) -> tuple:
        """v2 能力矩阵：声明该 layout 适配哪些 theme。

        返回 theme id 元组（"海洋柔光" / "月夜星河" / ...）。
        默认空 tuple = 全部兼容（v1 兼容）。
        子类可 override：例如 live-set 排除某些过于花哨的主题。

        校验逻辑见 core.layouts.compat.check_compatibility（双向校验）。
        """
        return ()

    # ---- 能力声明 (P1 R1a.3) ----
    # 每个 Layout 自报支持的画布比例、主题能力、分页策略与分类轴；
    # 这是 P1 R1a.3 grid-wrap 能力声明契约的入口。
    def capabilities(self) -> dict:
        """返回该布局的能力元数据。

        默认实现是「grid-wrap」P1 兼容路径。
        新布局（magazine-flow / live-set / learning-report）应重写本方法。
        """
        return {
            "supported_canvas_ids": ["9:16", "9:20"],
            "required_theme_capabilities": [],
            "supports_auto_pagination": False,
            "supports_manual_pages": False,
            "supports_grouping": ["none", "chars"],
            "page_policy_mode": "legacy-fixed-2",
            "max_density": {},     # {"section": N} 等
            # R4 Runtime v1：layout 接受的数据通道列表（来自 supported_channels
            # 类属性；子类重写 capabilities 时应一并返回）。
            "supported_channels": list(self.supported_channels),
        }
