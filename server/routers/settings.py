"""设置路由（/api/settings）。"""
from fastapi import APIRouter, Request

from server.api.errors import ApiError, map_repository_error
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    DataDirInspectRequest,
    DataDirInspectResponse,
    DataDirStatusResponse,
    DataDirSwitchRequest,
    DataDirSwitchResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
)
from server.dependencies import get_app_context
from server.ports.repositories import RepositoryError
from server.services.data_dir import (
    DataDirConflict,
    DataDirUnavailable,
    DataDirValidationFailed,
)
from server.services.settings import SettingsValidationFailed

router = APIRouter()


def _data_dir_error_response(req: Request, error: Exception):
    if isinstance(error, DataDirValidationFailed):
        return api_error_response(
            req, 400, ApiError("invalid_data_dir", str(error),
                               recovery="检查路径后重试"))
    if isinstance(error, DataDirConflict):
        return api_error_response(
            req, 409, ApiError(
                "data_dir_conflict", str(error),
                details={"existing_items": error.existing_items},
                recovery="确认使用已有数据，或选择空目录迁移"))
    return api_error_response(
        req, 503, ApiError("data_dir_unavailable", str(error),
                           recovery="检查磁盘权限后重试"))


@router.get("/api/settings", response_model=SettingsResponse)
def api_settings_get(req: Request):
    try:
        return get_app_context(req).settings_service.get()
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return api_error_response(req, status_code, api_error)


@router.post("/api/settings", response_model=SettingsUpdateResponse)
def api_settings_update(req: Request, new_settings: SettingsUpdateRequest):
    context = get_app_context(req)
    payload = (new_settings.model_dump(exclude_unset=True)
               if isinstance(new_settings, SettingsUpdateRequest) else new_settings)
    try:
        settings = context.settings_service.update(payload)
    except SettingsValidationFailed as error:
        return api_error_response(
            req, 400, ApiError("invalid_settings", str(error)))
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return api_error_response(req, status_code, api_error)
    return {"ok": True, "settings": settings}


@router.get("/api/settings/data-dir", response_model=DataDirStatusResponse)
def api_data_dir_status(req: Request):
    return get_app_context(req).data_dir_service.status()


@router.post("/api/settings/data-dir/inspect", response_model=DataDirInspectResponse)
def api_data_dir_inspect(req: Request, body: DataDirInspectRequest):
    inspection = get_app_context(req).data_dir_service.inspect(body.path)
    return DataDirInspectResponse(
        path=str(inspection.path),
        valid=inspection.valid,
        message=inspection.message,
        exists=inspection.exists,
        is_current=inspection.is_current,
        parent_writable=inspection.parent_writable,
        has_existing_data=inspection.has_existing_data,
        existing_items=inspection.existing_items,
        will_initialize=inspection.will_initialize,
    )


@router.post("/api/settings/data-dir", response_model=DataDirSwitchResponse)
def api_data_dir_switch(req: Request, body: DataDirSwitchRequest):
    try:
        result = get_app_context(req).data_dir_service.switch(
            body.path, migrate=body.migrate, use_existing=body.use_existing)
    except (DataDirValidationFailed, DataDirConflict, DataDirUnavailable) as error:
        return _data_dir_error_response(req, error)
    return result
