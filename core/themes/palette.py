"""调色板（Palette）——纯颜色角色集合，不包含背景图和布局信息。

Palette v1 承载现有 5 个颜色角色 + 字体角色。
可从现有 flat Theme 构造，也可从 palette.json 独立加载。

R4 Runtime v2：Palette.to_style() 真正接到渲染管线（双轨过渡）。
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Tuple, Optional

if TYPE_CHECKING:
    from ..style import Style


@dataclass
class Palette:
    """纯颜色角色集合。与背景/布局/锚点完全解耦。

    从 Theme.styles 按页提取：一页一个 Palette 实例。
    theme.json 无 palette_ref 时自动从 styles 构造（兼容旧主题）。
    """
    # ---- 五颜色角色（对应 Style 同名字段）----
    text: Tuple[int, int, int]        # RGB(43,84,78) 歌名正文色
    label: Tuple[int, int, int]       # RGB(36,110,96) 标签文字色
    pill: Tuple[int, int, int, int]   # RGBA(188,224,210,130) 标签底色
    line: Tuple[int, int, int]        # RGB(232,146,118) 下划线/装饰
    mist: Tuple[int, int, int, int]   # RGBA(255,255,255,66) 柔光覆盖

    # ---- 字体角色（v1 四个，旧 font_song/font_label 兼容）----
    font_title: Optional[str] = None      # 刊头/大标题（None = 使用 font_label）
    font_label_role: Optional[str] = None # 分类标签（None = 使用 font_label）
    font_song: Optional[str] = None       # 歌名正文（None = 使用 font_song）
    font_note: Optional[str] = None       # 注释/日期/序号（None = 使用 font_song）

    # ---- 元数据 ----
    name: str = ""                      # palette 名（如 "海洋柔光"）
    source: str = "theme"               # "theme" | "palette.json"

    @staticmethod
    def from_style(page_num: int, style, name: str = "") -> "Palette":
        """从 Style 对象构造 Palette（双向兼容：Style 字段 = Palette 字段）。"""
        return Palette(
            name=name or f"page{page_num}",
            text=style.text,
            label=style.label,
            pill=style.pill,
            line=style.line,
            mist=style.mist,
            source="theme",
        )

    def to_style_dict(self) -> dict:
        """转换为可合并到 Style 的字段字典（预留，供 Skin 覆盖 Palette 时使用）。"""
        return {
            "text": self.text,
            "label": self.label,
            "pill": self.pill,
            "line": self.line,
            "mist": self.mist,
        }

    def to_style(self) -> "Style":
        """R4 Runtime v2: Palette → Style（frozen 5 角色）。

        用于 engine.render_page 接收 palette 后构造 Style。
        字体角色不进 Style（Style 旧契约只 5 颜色；字体由 ctx.font_song/font_label 传）。
        """
        from ..style import Style
        return Style(
            text=self.text,
            label=self.label,
            pill=self.pill,
            line=self.line,
            mist=self.mist,
        )
