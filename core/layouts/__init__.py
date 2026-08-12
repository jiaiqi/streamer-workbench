"""排版插件注册表。MVP 手写注册，后期如需再改目录扫描。

R4 Runtime v1：get_layout 支持按 DataChannel 过滤；list_layouts 返回
每个 layout 的 supported_channels 字段，方便前端 / 文档展示。
R4 Runtime v2：导出 LayoutPlan / LayoutAnalysis / PagePlan / SectionPlan / LayoutContext。
M0.2 (蓝图 v0.1)：新增 fullscreen-flow（全屏柔光绕排版）。
"""
from .grid_wrap import GridWrapLayout
from .magazine_flow import MagazineFlowLayout
from .live_set import LiveSetLayout
from .learning_report import LearningReportLayout
from .fullscreen_flow import FullscreenFlowLayout
from .channel import DataChannel, CHANNELS, normalize_channel, is_supported
from .plan import (
    LayoutAnalysis,
    LayoutPlan,
    PagePlan,
    SectionLayoutKind,
    SectionPlan,
)
from .ctx import LayoutContext

REGISTRY = {
    "grid-wrap": GridWrapLayout(),
    "magazine-flow": MagazineFlowLayout(),
    "live-set": LiveSetLayout(),
    "learning-report": LearningReportLayout(),
    "fullscreen-flow": FullscreenFlowLayout(),
}


def get_layout(layout_id: str, *, channel: DataChannel | None = None):
    """按 id 拿 layout；可选按 DataChannel 校验。

    - 不传 channel：保持 R0-R3 行为，仅校验 id 存在。
    - 传 channel：若 layout 不支持该 channel，抛 KeyError（带 supported_channels 提示）。
    """
    if layout_id not in REGISTRY:
        raise KeyError(f"未知排版「{layout_id}」，可选：{', '.join(REGISTRY)}")
    plugin = REGISTRY[layout_id]
    if channel is not None and not is_supported(plugin.supported_channels, channel):
        normalized = normalize_channel(channel)
        raise KeyError(
            f"排版「{layout_id}」不支持数据通道「{normalized}」；"
            f"已声明支持：{list(plugin.supported_channels) or '（未声明）'}"
        )
    return plugin


def list_layouts(*, channel: DataChannel | None = None) -> list[dict]:
    """列出所有 layout。channel 过滤时只返回支持该通道的 layout。

    返回 dict 字段：id / name / pages / supports_avoidance / supported_channels
    """
    rows = [
        {"id": lid, "name": p.name,
         "pages": p.pages,
         "supports_avoidance": p.supports_avoidance,
         "supported_channels": list(p.supported_channels)}
        for lid, p in REGISTRY.items()
    ]
    if channel is None:
        return rows
    normalized = normalize_channel(channel)
    return [r for r in rows if normalized in r["supported_channels"]]


def layout_params(layout_id: str):
    """排版插件的可调参数描述（ParamSpec），UI 据此动态生成参数面板。"""
    from dataclasses import asdict
    return [asdict(ps) for ps in get_layout(layout_id).params()]


__all__ = [
    "REGISTRY", "get_layout", "list_layouts", "layout_params",
    "DataChannel", "CHANNELS", "normalize_channel", "is_supported",
    # R4 Runtime v2
    "LayoutAnalysis", "LayoutPlan", "PagePlan", "SectionPlan", "SectionLayoutKind",
    "LayoutContext",
]
