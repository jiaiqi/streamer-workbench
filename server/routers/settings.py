"""设置路由（/api/settings）。"""
from fastapi import APIRouter, Request

from server.api.errors import map_repository_error
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
)
from server.dependencies import get_app_context
from server.ports.repositories import RepositoryError

router = APIRouter()


@router.get("/api/settings", response_model=SettingsResponse)
def api_settings_get(req: Request):
    return get_app_context(req).settings_repository.load().value


@router.post("/api/settings", response_model=SettingsUpdateResponse)
def api_settings_update(req: Request, new_settings: SettingsUpdateRequest):
    context = get_app_context(req)
    payload = (new_settings.model_dump(exclude_unset=True)
               if isinstance(new_settings, SettingsUpdateRequest) else new_settings)
    try:
        snapshot = context.settings_repository.load()
        settings = snapshot.value
        settings.update(payload)
        saved = context.settings_repository.save(settings, expected_revision=snapshot.revision)
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return api_error_response(req, status_code, api_error)
    return {"ok": True, "settings": saved.value}
