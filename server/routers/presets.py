"""预设路由（/api/presets*）。

R0.5：完整 CRUD——创建/完整更新/读取/复制/软删除，保存完整场景字段
（SongQuery、layout、palette、skin、canvas、params、export、color_overrides）。
Pydantic 类型化契约留给 R0.8，本批保持 dict 负载 + 数据层校验。
"""
from datetime import datetime

from fastapi import APIRouter, Response

from core.data.presets import (
    list_all, load, save, delete, duplicate,
    new_preset_id, _from_dict, _to_dict,
)

router = APIRouter()


@router.get("/api/presets")
def api_presets_list():
    return list_all()


@router.get("/api/presets/{preset_id}")
def api_presets_get(preset_id: str):
    p = load(preset_id)
    if p is None:
        return Response("预设不存在", status_code=404)
    return _to_dict(p)


@router.post("/api/presets")
def api_presets_save(payload: dict):
    """创建（无 id 时生成）或完整更新（有 id 时整体覆盖）预设。"""
    try:
        p = _from_dict(payload)
    except TypeError as e:
        return Response(f"预设字段不合法：{e}", status_code=400)
    if not p.id:
        p.id = new_preset_id()
    if not p.created_at:
        p.created_at = datetime.now().isoformat(timespec="seconds")
    try:
        save(p)
    except ValueError as e:
        return Response(str(e), status_code=400)
    return {"ok": True, "id": p.id, "updated_at": p.updated_at}


@router.post("/api/presets/{preset_id}/duplicate")
def api_presets_duplicate(preset_id: str, payload: dict = None):
    new_name = (payload or {}).get("name", "")
    p = duplicate(preset_id, new_preset_id(), new_name)
    if p is None:
        return Response("预设不存在", status_code=404)
    return {"ok": True, "id": p.id, "name": p.name}


@router.delete("/api/presets/{preset_id}")
def api_presets_delete(preset_id: str):
    if preset_id == "_default":
        return Response("默认预设不可删除", status_code=400)
    if not delete(preset_id):
        return Response("预设不存在", status_code=404)
    return {"ok": True}
