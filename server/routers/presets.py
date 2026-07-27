"""预设路由（/api/presets*）。"""
from fastapi import APIRouter, Request, Response

from server.deps import get_settings
from core.data.presets import list_all, load, save, delete, duplicate, Preset

router = APIRouter()


@router.get("/api/presets")
def api_presets_list():
    return list_all()


@router.get("/api/presets/{preset_id}")
def api_presets_get(preset_id: str):
    p = load(preset_id)
    if p is None:
        return Response("预设不存在", status_code=404)
    return p


@router.post("/api/presets")
def api_presets_save(payload: dict):
    p = Preset(
        id=payload.get("id", ""),
        name=payload.get("name", "未命名预设"),
        layout_id=payload.get("layout_id", "grid-wrap"),
    )
    save(p)
    return {"ok": True, "id": p.id}


@router.delete("/api/presets/{preset_id}")
def api_presets_delete(preset_id: str):
    delete(preset_id)
    return {"ok": True}
