"""预设路由（/api/presets*）。

R0.5：完整 CRUD——创建/完整更新/读取/复制/软删除，保存完整场景字段
（SongQuery、layout、palette、skin、canvas、params、export、color_overrides）。
Pydantic 类型化契约留给 R0.8，本批保持 dict 负载 + 数据层校验。
"""
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Request
from server.api.errors import ApiError, map_repository_error
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    OkResponse,
    PresetDuplicateRequest,
    PresetDuplicateResponse,
    PresetRequest,
    PresetResponse,
    PresetSaveResponse,
    PresetSummaryResponse,
)
from server.dependencies import get_app_context

from core.data.presets import (
    Preset,
    _from_dict,
    _to_dict,
    new_preset_id,
    validate_song_query,
)
from server.ports.repositories import RepositoryError

router = APIRouter()


def _payload_dict(payload) -> dict:
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


def _business_error(req: Request, status_code: int, code: str, message: str):
    return api_error_response(req, status_code, ApiError(code, message))


@router.get("/api/presets", response_model=list[PresetSummaryResponse])
def api_presets_list(req: Request):
    return [asdict(item) for item in get_app_context(req).preset_repository.list().value]


@router.get("/api/presets/{preset_id}", response_model=PresetResponse)
def api_presets_get(preset_id: str, req: Request):
    snapshot = get_app_context(req).preset_repository.get(preset_id)
    if snapshot is None:
        return _business_error(req, 404, "preset_not_found", "预设不存在")
    return _to_dict(snapshot.value)


@router.post("/api/presets", response_model=PresetSaveResponse)
def api_presets_save(payload: PresetRequest, req: Request):
    """创建（无 id 时生成）或完整更新（有 id 时整体覆盖）预设。"""
    try:
        p = _from_dict(_payload_dict(payload))
    except (TypeError, ValueError, AttributeError) as e:
        return _business_error(req, 400, "invalid_preset", f"预设字段不合法：{e}")
    if not p.id:
        p.id = new_preset_id()
    # `_default` 是唯一默认预设；客户端负载不能移除或伪造该身份标志。
    p.is_default = p.id == "_default"
    if not p.created_at:
        p.created_at = datetime.now().isoformat(timespec="seconds")
    try:
        validate_song_query(p.song_query)
        repository = get_app_context(req).preset_repository
        current = repository.get(p.id)
        repository.save(p, expected_revision=current.revision if current else None)
    except (TypeError, ValueError) as e:
        return _business_error(req, 400, "invalid_preset", str(e))
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return api_error_response(req, status_code, api_error)
    return {"ok": True, "id": p.id, "updated_at": p.updated_at}


@router.post("/api/presets/{preset_id}/duplicate", response_model=PresetDuplicateResponse)
def api_presets_duplicate(preset_id: str, req: Request,
                          payload: PresetDuplicateRequest | None = None):
    new_name = _payload_dict(payload).get("name", "") if payload is not None else ""
    repository = get_app_context(req).preset_repository
    if repository.get(preset_id) is None:
        return _business_error(req, 404, "preset_not_found", "预设不存在")
    target = Preset(id=new_preset_id(), name=new_name)
    try:
        saved = repository.duplicate(preset_id, target).value
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return api_error_response(req, status_code, api_error)
    return {"ok": True, "id": saved.id, "name": saved.name}


@router.delete("/api/presets/{preset_id}", response_model=OkResponse)
def api_presets_delete(preset_id: str, req: Request):
    if preset_id == "_default":
        return _business_error(req, 400, "default_preset_protected", "默认预设不可删除")
    repository = get_app_context(req).preset_repository
    current = repository.get(preset_id)
    if current is None:
        return _business_error(req, 404, "preset_not_found", "预设不存在")
    try:
        repository.delete(preset_id, expected_revision=current.revision)
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return api_error_response(req, status_code, api_error)
    return {"ok": True}
