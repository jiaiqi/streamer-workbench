"""预设 HTTP 适配层（/api/presets*）。"""
from dataclasses import asdict

from fastapi import APIRouter, Request
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    OkResponse,
    PresetDefaultResponse,
    PresetDuplicateRequest,
    PresetDuplicateResponse,
    PresetRequest,
    PresetResponse,
    PresetSaveResponse,
    PresetSummaryResponse,
)
from server.dependencies import get_app_context

from core.data.presets import _to_dict
from server.services.presets import (
    PresetNotFound,
    PresetProtected,
    PresetServiceError,
    PresetValidationFailed,
)

router = APIRouter()


def _payload_dict(payload) -> dict:
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


def _service_error(req: Request, error: PresetServiceError):
    if isinstance(error, PresetNotFound):
        status_code, code = 404, "preset_not_found"
    elif isinstance(error, PresetProtected):
        status_code, code = 400, "default_preset_protected"
    elif isinstance(error, PresetValidationFailed):
        status_code, code = 400, "invalid_preset"
    else:
        status_code, code = 500, "preset_error"
    return api_error_response(req, status_code, ApiError(code, str(error)))


@router.get("/api/presets", response_model=list[PresetSummaryResponse])
def api_presets_list(req: Request):
    return [asdict(item) for item in get_app_context(req).preset_service.list()]


@router.get("/api/presets/{preset_id}", response_model=PresetResponse)
def api_presets_get(preset_id: str, req: Request):
    try:
        preset = get_app_context(req).preset_service.get(preset_id)
    except PresetServiceError as error:
        return _service_error(req, error)
    return _to_dict(preset)


@router.post("/api/presets", response_model=PresetSaveResponse)
def api_presets_save(payload: PresetRequest, req: Request):
    """创建（无 id 时生成）或完整更新（有 id 时整体覆盖）预设。"""
    try:
        result = get_app_context(req).preset_service.save(_payload_dict(payload))
    except PresetServiceError as error:
        return _service_error(req, error)
    return {"ok": True, "id": result.preset.id,
            "updated_at": result.preset.updated_at}


@router.post("/api/presets/{preset_id}/duplicate", response_model=PresetDuplicateResponse)
def api_presets_duplicate(preset_id: str, req: Request,
                          payload: PresetDuplicateRequest | None = None):
    new_name = _payload_dict(payload).get("name", "") if payload is not None else ""
    try:
        result = get_app_context(req).preset_service.duplicate(
            preset_id, name=new_name)
    except PresetServiceError as error:
        return _service_error(req, error)
    return {"ok": True, "id": result.preset.id,
            "name": result.preset.name}


@router.delete("/api/presets/{preset_id}", response_model=OkResponse)
def api_presets_delete(preset_id: str, req: Request):
    try:
        get_app_context(req).preset_service.delete(preset_id)
    except PresetServiceError as error:
        return _service_error(req, error)
    return {"ok": True}


@router.post(
    "/api/presets/{preset_id}/default",
    response_model=PresetDefaultResponse,
)
def api_presets_set_default(preset_id: str, req: Request):
    try:
        result = get_app_context(req).preset_service.set_default(preset_id)
    except PresetServiceError as error:
        return _service_error(req, error)
    return {"ok": True, "id": result.preset_id}
