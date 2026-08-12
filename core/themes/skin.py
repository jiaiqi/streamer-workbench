"""皮肤（Skin）—— 主题对某布局的适配层。

Skin 连接 Palette（纯颜色）与 Layout（纯结构）：
- 背景图路径 + 页面策略
- 主题主体声明（subjects / anchors / avoid zones）
- Palette 颜色到布局扩展角色的映射
- 布局参数的布局级覆盖默认值

旧 theme.json 在加载时可动态适配为临时 Skin（兼容期）。

R4 Runtime v2：Skin.from_palette_and_layout() 工厂 + Skin.apply_to_style() 真实接线。
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from ..style import Style
    from .palette import Palette


@dataclass
class Skin:
    """主题 × 布局适配实例。

    每个 (theme, layout_id) 一个 Skin 实例。
    theme.json 无 skin 覆盖时使用 fallback Skin（从 theme 直接推导）。
    """
    theme_name: str
    layout_id: str

    # ---- 背景 ----
    backgrounds: Dict[str, str] = field(default_factory=dict)  # {"1": "bg1.png", "2": "bg2.png"}
    bg_strategy: str = "fixed"         # "fixed" | "cycle" | "extend"

    # ---- 视觉主体（P4 起用）----
    # 声明背景中的主体位置，布局引擎据此绕排
    subjects: list = field(default_factory=list)

    # ---- 柔光 ----
    mist_bottom_avoid: int = 1498      # 避让版柔光底边（+ content_offset）
    mist_bottom_normal: int = 1410     # 标准版柔光底边（+ content_offset）

    # ---- 布局参数默认覆盖 ----
    # 此 Skin 对该布局的推荐参数值。用户可覆盖。
    param_overrides: dict = field(default_factory=dict)

    # ---- 扩展颜色角色（布局可选的额外颜色）----
    # key = 角色名（如 "card_bg"），value = RGBA tuple
    extra_colors: dict = field(default_factory=dict)

    # ---- 元数据 ----
    compatibility: str = "recommended"  # "recommended" | "compatible" | "experimental"
    source: str = "theme"               # "theme" | "skin.json"

    @staticmethod
    def from_theme(theme, layout_id: str = "grid-wrap") -> "Skin":
        """从现有 Theme 构造 fallback Skin（兼容旧 theme.json 加载）。

        所有新字段取缺省值，保证旧主题可渲染。
        """
        return Skin(
            theme_name=theme.name,
            layout_id=layout_id,
            backgrounds=theme.backgrounds.copy(),
            mist_bottom_avoid=1498,
            mist_bottom_normal=1410,
            source="theme",
        )

    @staticmethod
    def from_palette_and_layout(palette: "Palette", layout_id: str,
                                 theme_name: str = "",
                                 backgrounds: Optional[Dict[str, str]] = None) -> "Skin":
        """R4 Runtime v2: 工厂方法 — 从 Palette + layout_id 构造 Skin。

        用于 engine.render_page 接收 palette 后构造 Skin。
        backgrounds 来自 theme（可选；缺省空 dict）。
        """
        return Skin(
            theme_name=theme_name or palette.name or "unknown",
            layout_id=layout_id,
            backgrounds=backgrounds or {},
            source="palette-factory",  # 标识来源便于调试
        )

    def apply_to_style(self, base: "Style", palette: "Palette") -> "Style":
        """R4 Runtime v2: 把 Skin 覆盖应用到基础 Style。

        优先级：extra_colors（Skin 自报扩展角色） > palette 5 角色 > base 5 角色。
        实际只有 5 角色进 Style，extra_colors 暂存留待 layout 读取。

        v1 兼容：不传 palette 时返 base 拷贝（保留旧行为）。
        """
        from ..style import Style
        if palette is None:
            # 防御：v1 兼容路径
            return Style(
                text=base.text, label=base.label, pill=base.pill,
                line=base.line, mist=base.mist,
            )
        return Style(
            text=palette.text,
            label=palette.label,
            pill=palette.pill,
            line=palette.line,
            mist=palette.mist,
        )
