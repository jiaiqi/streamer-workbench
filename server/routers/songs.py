"""歌曲管理路由（/api/songs*）。"""

from fastapi import APIRouter, UploadFile, File, Request, Response

from core.data.tabs import MAX_FILE_BYTES
from server.api.errors import ApiError
from server.api.handlers import api_error_response
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
from server.services.songs import (
    SongConflict,
    SongNotFound,
    SongServiceError,
    SongValidationFailed,
    song_values,
)
from server.services.tabs import (
    TabNotFound,
    TabServiceError,
    TabValidationFailed,
)

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


def _tab_service_error(request: Request, error: TabServiceError):
    status_code = 404 if isinstance(error, TabNotFound) else 400
    if not isinstance(error, (TabNotFound, TabValidationFailed)):
        status_code = 500
    code = "tab_not_found" if status_code == 404 else "tab_validation_failed"
    if status_code == 500:
        code = "tab_error"
    return api_error_response(
        request, status_code,
        ApiError(code, str(error), recovery="检查曲谱文件和歌曲状态后重试"))


def _library(context):
    repository = context.song_repository
    if hasattr(repository, "load"):
        snapshot = repository.load()
        setattr(snapshot.value, "_repository_revision", snapshot.revision)
        return snapshot.value
    return repository


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


@router.post("/api/songs/seed-sample", response_model=SongMutationResponse)
def api_songs_seed_sample(req: Request):
    """仅在曲库为空时载入内置样例曲库（核心数据写入路径）。

    注：必须在 /api/songs/{song_id} 之前注册，否则会被路径参数拦截。
    非空库返回 200 with added=[]；首次空库返回新加入的歌曲列表。
    """
    result = get_app_context(req).song_service.seed_sample_songs()
    if result.song is None:
        # 边界：不可达；防御兜底
        return {"ok": True, "song": {"title": "", "artists": [], "lyricist": "",
                                     "composer": "", "key": "", "capo": None,
                                     "difficulty": "", "tabs": "", "status": "draft",
                                     "tags": [], "pinyin": "", "added_at": "",
                                     "notes": "", "learned_at": "", "tab_files": [],
                                     "section": None, "id": ""},
                "active": 0, "draft": 0, "added": []}
    song_d = {
        "id": result.song.id,
        "title": result.song.title,
        "artists": list(result.song.artists),
        "lyricist": result.song.lyricist,
        "composer": result.song.composer,
        "key": result.song.key,
        "capo": result.song.capo,
        "difficulty": result.song.difficulty,
        "tabs": result.song.tabs,
        "status": result.song.status,
        "tags": list(result.song.tags),
        "pinyin": result.song.pinyin,
        "added_at": result.song.added_at,
        "notes": result.song.notes,
        "learned_at": result.song.learned_at,
        "tab_files": list(result.song.tab_files),
        "section": result.song.section,
    }
    return {"ok": True, "song": song_d,
            "active": result.active, "draft": result.draft,
            "added": [s.title for s in result.added]}


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


@router.post("/api/songs/{identity}/tabs")
async def api_tab_upload(req: Request, identity: str, file: UploadFile = File(...)):
    context = get_app_context(req)
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        result = context.tab_service.upload(
            identity, file.filename or "tab.png", data, file.content_type)
    except TabServiceError as error:
        return _tab_service_error(req, error)
    return {"ok": True, "song_id": result.song_id, "title": result.title,
            "file": result.file, "tab_files": list(result.tab_files)}


@router.get("/api/songs/{identity}/tabs")
def api_tab_list(req: Request, identity: str):
    try:
        result = get_app_context(req).tab_service.list(identity)
    except TabServiceError as error:
        return _tab_service_error(req, error)
    return {"song_id": result.song_id, "title": result.title,
            "tab_files": list(result.tab_files)}


@router.delete("/api/songs/{identity}/tabs")
def api_tab_delete(req: Request, identity: str, file: str):
    try:
        result = get_app_context(req).tab_service.delete(identity, file)
    except TabServiceError as error:
        return _tab_service_error(req, error)
    return {"ok": True, "song_id": result.song_id, "title": result.title,
            "tab_files": list(result.tab_files)}
