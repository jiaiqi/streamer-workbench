"""皮肤（Skin）—— 主题对某布局的适配层。

Skin 连接 Palette（纯颜色）与 Layout（纯结构）：
- 背景图路径 + 页面策略
- 主题主体声明（subjects / anchors / avoid zones）
- Palette 颜色到布局扩展角色的映射
- 布局参数的布局级覆盖默认值

旧 theme.json 在加载时可动态适配为临时 Skin（兼容期）。
"""
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Skin:
    """主题 × 布局适配实例。

    每个 (theme, layout_id) 一个 Skin 实例。
    theme.json 无 skin 覆盖时使用 fallback Skin（从 theme 直接推导）。
    """
    theme_name: str
    layout_id: str

    # ---- 背景 ----
    backgrounds: Dict[str, str]        # {"1": "bg1.png", "2": "bg2.png"}
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
