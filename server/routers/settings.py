"""设置路由（/api/settings）。"""
from fastapi import APIRouter, Request, Response

from server.deps import get_settings
from server.deps import _save_settings as save_settings

router = APIRouter()


@router.get("/api/settings")
def api_settings_get(req: Request):
    return get_settings(req.app.state)


@router.post("/api/settings")
def api_settings_update(req: Request, new_settings: dict):
    settings = get_settings(req.app.state)
    settings.update(new_settings)
    save_settings(settings)
    return {"ok": True, "settings": settings}
