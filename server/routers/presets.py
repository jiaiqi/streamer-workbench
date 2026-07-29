"""预设路由（/api/presets*）。

R0.5：完整 CRUD——创建/完整更新/读取/复制/软删除，保存完整场景字段
（SongQuery、layout、palette、skin、canvas、params、export、color_overrides）。
Pydantic 类型化契约留给 R0.8，本批保持 dict 负载 + 数据层校验。
"""
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Request, Response
from server.dependencies import get_app_context

from core.data.presets import Preset, new_preset_id, _from_dict, _to_dict
from server.ports.repositories import RepositoryConflict, RepositoryError

router = APIRouter()


@router.get("/api/presets")
def api_presets_list(req: Request):
    return [asdict(item) for item in get_app_context(req).preset_repository.list().value]


@router.get("/api/presets/{preset_id}")
def api_presets_get(preset_id: str, req: Request):
    snapshot = get_app_context(req).preset_repository.get(preset_id)
    if snapshot is None:
        return Response("预设不存在", status_code=404)
    return _to_dict(snapshot.value)


@router.post("/api/presets")
def api_presets_save(payload: dict, req: Request):
    """创建（无 id 时生成）或完整更新（有 id 时整体覆盖）预设。"""
    try:
        p = _from_dict(payload)
    except (TypeError, ValueError, AttributeError) as e:
        return Response(f"预设字段不合法：{e}", status_code=400)
    if not p.id:
        p.id = new_preset_id()
    # `_default` 是唯一默认预设；客户端负载不能移除或伪造该身份标志。
    p.is_default = p.id == "_default"
    if not p.created_at:
        p.created_at = datetime.now().isoformat(timespec="seconds")
    try:
        repository = get_app_context(req).preset_repository
        current = repository.get(p.id)
        repository.save(p, expected_revision=current.revision if current else None)
    except (TypeError, ValueError, RepositoryError) as e:
        return Response(str(e), status_code=400)
    return {"ok": True, "id": p.id, "updated_at": p.updated_at}


@router.post("/api/presets/{preset_id}/duplicate")
def api_presets_duplicate(preset_id: str, req: Request, payload: dict = None):
    new_name = (payload or {}).get("name", "")
    repository = get_app_context(req).preset_repository
    if repository.get(preset_id) is None:
        return Response("预设不存在", status_code=404)
    target = Preset(id=new_preset_id(), name=new_name)
    try:
        saved = repository.duplicate(preset_id, target).value
    except RepositoryError as e:
        return Response(str(e), status_code=400)
    return {"ok": True, "id": saved.id, "name": saved.name}


@router.delete("/api/presets/{preset_id}")
def api_presets_delete(preset_id: str, req: Request):
    if preset_id == "_default":
        return Response("默认预设不可删除", status_code=400)
    repository = get_app_context(req).preset_repository
    current = repository.get(preset_id)
    if current is None:
        return Response("预设不存在", status_code=404)
    try:
        repository.delete(preset_id, expected_revision=current.revision)
    except RepositoryConflict as e:
        return Response(str(e), status_code=409)
    except RepositoryError as e:
        return Response(str(e), status_code=400)
    return {"ok": True}
