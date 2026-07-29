"""歌曲管理路由（/api/songs*）。"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Response

from server.api.song_models import (
    SongCreateRequest,
    SongDeleteResponse,
    SongEditableFields,
    SongLegacyDeleteResponse,
    SongLegacyIdentityRequest,
    SongLegacyStatusRequest,
    SongLegacyStatusResponse,
    SongLegacyUpdateRequest,
    SongMutationResponse,
    SongResponse,
    SongUpdateResponse,
    SongsListResponse,
    SongsSummaryResponse,
    SongStatusRequest,
)
from server.dependencies import get_app_context
from server.ports.repositories import RepositoryConflict, RepositoryError
from server.services.songs import (
    SongConflict,
    SongNotFound,
    SongServiceError,
    SongValidationFailed,
    song_values,
)
from core.data.events import append_event, _normalize_timestamp
from core.data import tabs as tabs_store

router = APIRouter()


def _payload_dict(payload) -> dict:
    """HTTP 使用 Pydantic；保留内部 Python/旧单元夹具的 dict 调用。"""
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


def _song_dict(s) -> dict:
    return song_values(s)


def _song_service_error(error: SongServiceError):
    if isinstance(error, SongNotFound):
        status_code = 404
    elif isinstance(error, SongConflict):
        status_code = 409
    elif isinstance(error, SongValidationFailed):
        status_code = 400
    else:
        status_code = 500
    return Response(str(error), status_code=status_code)


def _save_library(context, library):
    repository = context.song_repository
    if hasattr(repository, "load") and not isinstance(repository, type(library)):
        try:
            repository.save(
                library, expected_revision=getattr(library, "_repository_revision", None))
        except RepositoryConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RepositoryError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    else:  # 仅供旧单元夹具兼容；正式 AppContext 始终注入 Repository port。
        repository.save(str(context.paths.songs_json),
                        backup_dir=str(context.paths.backups_dir), backup_count=20)


def _library(context):
    repository = context.song_repository
    if hasattr(repository, "load"):
        snapshot = repository.load()
        setattr(snapshot.value, "_repository_revision", snapshot.revision)
        return snapshot.value
    return repository


def _events_path(context):
    return str(context.paths.events_jsonl)


def _append_event(context, event_type, **kwargs):
    store = getattr(context, "event_store", None)
    if store is None:
        return append_event(_events_path(context), event_type, **kwargs)
    event = {
        "schema_version": 2,
        "event_id": kwargs.pop("event_id", None) or f"evt_{uuid.uuid4().hex}",
        "occurred_at": _normalize_timestamp(kwargs.pop("occurred_at", None)),
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "type": event_type,
        "source": kwargs.pop("source", "songs-api"),
    }
    for key in ("song_id", "title_snapshot", "meta"):
        value = kwargs.get(key)
        if value is not None:
            event[key] = value
    return store.append(event).event


@router.get("/api/songs", response_model=SongsSummaryResponse)
def api_songs(req: Request):
    library = _library(get_app_context(req))
    from server.deps import _count_by_len
    return {"total": len(library.mastered()),
            "by_len": _count_by_len(library)}


@router.get("/api/songs/list", response_model=SongsListResponse)
def api_songs_list(req: Request, status: str = None):
    library = _library(get_app_context(req))
    songs = library.songs
    if status:
        songs = [s for s in songs if s.status == status]
    return {"total": len(songs),
            "active": library.count_active(),
            "draft": library.count_draft(),
            "songs": [_song_dict(s) for s in songs]}


@router.post("/api/songs/status", response_model=SongLegacyStatusResponse)
def api_songs_status(req: Request, payload: SongLegacyStatusRequest):
    payload = _payload_dict(payload)
    context = get_app_context(req)
    title = (payload.get("title") or "").strip()
    status = (payload.get("status") or "").strip()
    try:
        result = context.song_service.set_status_by_title(title, status)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "title": title, "status": status,
            "active": result.active, "draft": result.draft}


@router.post("/api/songs/update", response_model=SongUpdateResponse)
def api_songs_update(req: Request, payload: SongLegacyUpdateRequest):
    payload = _payload_dict(payload)
    context = get_app_context(req)
    title = (payload.get("title") or "").strip()
    try:
        result = context.song_service.update_by_title(
            title, payload.get("fields") or {})
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song": _song_dict(result.song)}


@router.post("/api/songs/add", response_model=SongMutationResponse)
def api_songs_add(req: Request, payload: SongCreateRequest):
    payload = _payload_dict(payload)
    context = get_app_context(req)
    try:
        result = context.song_service.create(payload)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song": _song_dict(result.song),
            "active": result.active, "draft": result.draft}


@router.post("/api/songs/delete", response_model=SongLegacyDeleteResponse)
def api_songs_delete(req: Request, payload: SongLegacyIdentityRequest):
    payload = _payload_dict(payload)
    context = get_app_context(req)
    title = (payload.get("title") or "").strip()
    try:
        result = context.song_service.delete_by_title(title)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "title": title,
            "active": result.active, "draft": result.draft}


# ── Song ID 主接口 ──

@router.get("/api/songs/{song_id}", response_model=SongResponse)
def api_song_get_by_id(req: Request, song_id: str):
    """按不可变 ID 获取歌曲；新消费者不得再用 title 定位资源。"""
    library = _library(get_app_context(req))
    song = library.get_by_id(song_id)
    if song is None:
        return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
    return _song_dict(song)


@router.patch("/api/songs/{song_id}", response_model=SongUpdateResponse)
def api_song_update_by_id(req: Request, song_id: str, payload: SongEditableFields):
    """按不可变 ID 更新歌曲，允许修改 title 但禁止修改 id。"""
    context = get_app_context(req)
    payload = _payload_dict(payload)
    try:
        result = context.song_service.update_by_id(song_id, payload)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song": _song_dict(result.song)}


@router.patch("/api/songs/{song_id}/status", response_model=SongMutationResponse)
def api_song_status_by_id(req: Request, song_id: str, payload: SongStatusRequest):
    """按不可变 ID 修改 active/draft 状态。"""
    context = get_app_context(req)
    payload = _payload_dict(payload)
    status = (payload.get("status") or "").strip()
    try:
        result = context.song_service.set_status_by_id(song_id, status)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song": _song_dict(result.song),
            "active": result.active, "draft": result.draft}


@router.delete("/api/songs/{song_id}", response_model=SongDeleteResponse)
def api_song_delete_by_id(req: Request, song_id: str):
    """按不可变 ID 删除歌曲；历史事件保留 ID 与 title_snapshot。"""
    context = get_app_context(req)
    try:
        result = context.song_service.delete_by_id(song_id)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song_id": result.song_id,
            "title_snapshot": result.title_snapshot,
            "active": result.active, "draft": result.draft}


# ── 曲谱附件 ──

def _resolve_song_identity(library, identity: str):
    """R0.5：ID 主查找，title 仅作为迁移期兼容回退。"""
    return library.get_by_id(identity) or library.get(identity)


@router.post("/api/songs/{identity}/tabs")
async def api_tab_upload(req: Request, identity: str, file: UploadFile = File(...)):
    context = get_app_context(req)
    library = _library(context)
    song = _resolve_song_identity(library, identity)
    if song is None:
        return Response(f"未找到歌曲：{identity}", status_code=404)
    data = await file.read()
    try:
        rel = tabs_store.save_tab(str(context.paths.tabs_dir), song.id, file.filename or "tab.png", data)
    except ValueError as e:
        return Response(str(e), status_code=400)
    song.tab_files.append(rel)
    _save_library(context, library)
    _append_event(context, "song_edited", song_id=song.id,
                 title_snapshot=song.title,
                 meta={"changes": [{"field": "tab_files", "old": None, "new": rel}]},
                 source="tabs-api")
    return {"ok": True, "song_id": song.id, "title": song.title,
            "file": rel, "tab_files": song.tab_files}


@router.get("/api/songs/{identity}/tabs")
def api_tab_list(req: Request, identity: str):
    library = _library(get_app_context(req))
    song = _resolve_song_identity(library, identity)
    if song is None:
        return Response(f"未找到歌曲：{identity}", status_code=404)
    return {"song_id": song.id, "title": song.title, "tab_files": song.tab_files}


@router.delete("/api/songs/{identity}/tabs")
def api_tab_delete(req: Request, identity: str, file: str):
    context = get_app_context(req)
    library = _library(context)
    song = _resolve_song_identity(library, identity)
    if song is None:
        return Response(f"未找到歌曲：{identity}", status_code=404)
    if file not in song.tab_files:
        return Response(f"曲谱不存在：{file}", status_code=404)
    song.tab_files.remove(file)
    tabs_store.delete_tab(str(context.paths.tabs_dir), song.id, file)
    _save_library(context, library)
    _append_event(context, "song_edited", song_id=song.id,
                 title_snapshot=song.title,
                 meta={"changes": [{"field": "tab_files", "old": file, "new": None}]},
                 source="tabs-api")
    return {"ok": True, "song_id": song.id, "title": song.title,
            "tab_files": song.tab_files}
