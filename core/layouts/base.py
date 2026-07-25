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
    page_capacity: int = 1920            # 自动分页时单页最大内容高度(px)
    supports_avoidance: bool = True      # 是否支持 avoid_zones 避让

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
