"""设置路由（/api/settings）。"""
from fastapi import APIRouter, Request, Response

from server.dependencies import get_app_context
from server.deps import save_settings

router = APIRouter()


@router.get("/api/settings")
def api_settings_get(req: Request):
    return get_app_context(req).settings_repository


@router.post("/api/settings")
def api_settings_update(req: Request, new_settings: dict):
    context = get_app_context(req)
    settings = context.settings_repository
    settings.update(new_settings)
    save_settings(str(context.paths.settings_json), settings)
    return {"ok": True, "settings": settings}
