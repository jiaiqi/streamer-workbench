"""排版插件注册表。MVP 手写注册，后期如需再改目录扫描。"""
from .grid_wrap import GridWrapLayout

REGISTRY = {
    "grid-wrap": GridWrapLayout(),
}


def get_layout(layout_id: str):
    if layout_id not in REGISTRY:
        raise KeyError(f"未知排版「{layout_id}」，可选：{', '.join(REGISTRY)}")
    return REGISTRY[layout_id]


def list_layouts():
    return [{"id": lid, "name": p.name} for lid, p in REGISTRY.items()]
