"""排版插件基类 + 参数描述。

每个排版一个模块。现有「全行网格绕排版」(grid-wrap) 是原 build_playlist.py
排版逻辑移植，作为第一个插件。新排版（便签拼贴/歌手分区…）写的时候，
胶囊标签、网格、绕排这些「零件」从 DrawContext 开箱即用，只写布局差异。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class ParamSpec:
    """暴露给右侧参数面板的可调项，UI 据此动态生成控件。"""
    key: str            # 对应 CanvasSpec 字段或插件自有参数
    label: str          # 显示名，如「歌名字号」
    kind: str           # "int" | "color" | "bool" | "choice"
    default: object
    min: int = None
    max: int = None
    choices: list = None


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

    # ---- 额外颜色角色 ----
    # 排版可声明自己需要的扩展颜色（如卡片背景、装饰色）。
    # 子类重写此方法返回角色名列表；theme.json 可选的 extra 字段提供对应值；
    # 未提供则回退到内置默认色。
    def extra_colors(self) -> dict:
        return {}

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
        }
