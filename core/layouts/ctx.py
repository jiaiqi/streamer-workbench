"""R4 Runtime v2: LayoutContext — 给 plan() / analyze() 用的非绘图上下文。

为什么与 DrawContext 分开：
- DrawContext 依赖 PIL ImageDraw + ImageFont（渲染时才有）
- plan/analyze 只算元数据，不画图——走轻量 ctx，零 PIL 依赖
- 同样可以序列化、可哈希

字段：
  canvas              CanvasSpec（画布尺寸 / 避让区 / 字号）
  parameters          dict（来自 RenderDocument.parameters）
  theme_capabilities  list[str]（主题能力名；v2 阶段默认 []）
  palette             Palette（v3 启用；v2 阶段保留为 None）
  skin                Skin（v3 启用；v2 阶段保留为 None）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from ..spec import CanvasSpec


@dataclass(frozen=True)
class LayoutContext:
    """LayoutContext: 给 plan() / analyze() 用的非绘图上下文（不可变）。"""
    canvas: "CanvasSpec"
    parameters: dict = field(default_factory=dict)
    theme_capabilities: Tuple[str, ...] = ()
    palette: Optional["Palette"] = None    # noqa: F821
    skin: Optional["Skin"] = None          # noqa: F821


__all__ = ["LayoutContext"]
