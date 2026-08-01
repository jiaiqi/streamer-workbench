"""排版插件注册表。MVP 手写注册，后期如需再改目录扫描。"""
from .grid_wrap import GridWrapLayout
from .magazine_flow import MagazineFlowLayout
from .live_set import LiveSetLayout
from .learning_report import LearningReportLayout

REGISTRY = {
    "grid-wrap": GridWrapLayout(),
    "magazine-flow": MagazineFlowLayout(),
    "live-set": LiveSetLayout(),
    "learning-report": LearningReportLayout(),
}


def get_layout(layout_id: str):
    if layout_id not in REGISTRY:
        raise KeyError(f"未知排版「{layout_id}」，可选：{', '.join(REGISTRY)}")
    return REGISTRY[layout_id]


def list_layouts():
    return [{"id": lid, "name": p.name,
             "pages": p.pages,
             "supports_avoidance": p.supports_avoidance}
            for lid, p in REGISTRY.items()]


def layout_params(layout_id: str):
    """排版插件的可调参数描述（ParamSpec），UI 据此动态生成参数面板。"""
    from dataclasses import asdict
    return [asdict(ps) for ps in get_layout(layout_id).params()]
