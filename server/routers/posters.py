"""R1a.1 Poster HTTP 适配层（/api/posters*）。

路由表：
- GET    /api/posters              列出已保存海报摘要
- POST   /api/posters              创建或覆盖更新（id 缺则生成）
- GET    /api/posters/{id}         读取完整 PosterDocument
- DELETE /api/posters/{id}         软删除
- POST   /api/posters/{id}/resolve 解析 SongSource → 歌曲快照列表

并发写由 expected_revision CAS 在 service 层处理；HTTP 层只做翻译。
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from core.data.posters import PosterDocument
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    OkResponse,
    PosterRequest,
    PosterResolveResponse,
    PosterResponse,
    PosterSaveResponse,
    PosterSummaryResponse,
)
from server.dependencies import get_app_context
from server.services.posters import (
    PosterNotFound,
    PosterServiceError,
    PosterValidationFailed,
)

router = APIRouter()


def _payload_dict(payload) -> dict:
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


def _service_error(req: Request, error: PosterServiceError):
    if isinstance(error, PosterNotFound):
        status_code, code = 404, "poster_not_found"
    elif isinstance(error, PosterValidationFailed):
        status_code, code = 400, "invalid_poster"
    else:
        status_code, code = 500, "poster_error"
    return api_error_response(req, status_code, ApiError(code, str(error)))


@router.get("/api/posters", response_model=list[PosterSummaryResponse])
def api_posters_list(req: Request):
    items = get_app_context(req).poster_service.list()
    return [asdict(item) for item in items]


@router.get("/api/posters/{poster_id}", response_model=PosterResponse)
def api_posters_get(poster_id: str, req: Request):
    """完整 PosterDocument + revision。revision 用于客户端 CAS 自动保存。"""
    try:
        poster, revision = get_app_context(req).poster_service.get_with_revision(poster_id)
    except PosterServiceError as error:
        return _service_error(req, error)
    payload = poster.to_dict()
    payload["revision"] = revision
    return payload


@router.post("/api/posters", response_model=PosterSaveResponse)
def api_posters_save(payload: PosterRequest, req: Request):
    """创建或整体覆盖：id 缺则生成，否则按 repository CAS 更新。"""
    try:
        result = get_app_context(req).poster_service.save(_payload_dict(payload))
    except PosterServiceError as error:
        return _service_error(req, error)
    return {
        "ok": True,
        "id": result.poster.id,
        "revision": result.revision,
        "updated_at": result.poster.updated_at,
    }


@router.delete("/api/posters/{poster_id}", response_model=OkResponse)
def api_posters_delete(poster_id: str, req: Request):
    try:
        get_app_context(req).poster_service.delete(poster_id)
    except PosterServiceError as error:
        return _service_error(req, error)
    return {"ok": True}


@router.post(
    "/api/posters/{poster_id}/resolve",
    response_model=PosterResolveResponse,
)
def api_posters_resolve(poster_id: str, req: Request):
    """将已保存 Poster 的 SongSource + selected_song_ids 解析为不可变快照列表。

    预览与导出共享此结果；missing_song_ids 报告不在曲库的 song_id 引用。
    """
    try:
        result = get_app_context(req).poster_service.resolve(poster_id)
    except PosterServiceError as error:
        return _service_error(req, error)
    return {
        "poster_id": poster_id,
        "songs": [
            {
                "id": snap.id,
                "title": snap.title,
                "artists": list(snap.artists),
                "section": snap.section,
            }
            for snap in result.songs
        ],
        "missing_song_ids": list(result.missing_song_ids),
    }
