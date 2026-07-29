"""设置路由（/api/settings）。"""
from fastapi import APIRouter, HTTPException, Request

from server.dependencies import get_app_context
from server.ports.repositories import RepositoryConflict, RepositoryError

router = APIRouter()


@router.get("/api/settings")
def api_settings_get(req: Request):
    return get_app_context(req).settings_repository.load().value


@router.post("/api/settings")
def api_settings_update(req: Request, new_settings: dict):
    context = get_app_context(req)
    try:
        snapshot = context.settings_repository.load()
        settings = snapshot.value
        settings.update(new_settings)
        saved = context.settings_repository.save(settings, expected_revision=snapshot.revision)
    except RepositoryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"ok": True, "settings": saved.value}
