"""歌曲管理路由（/api/songs*）。

P1-A4 收口：title 路由加 Deprecation + Sunset header，新消费者必须走 song_id 主键路由。
"""

import json
from fastapi import APIRouter, UploadFile, File, Path, Request, Response
from dataclasses import asdict

# Sunset: 固定日期 2027-02-23；2026-08-23 起 6 个月内为兼容窗口
# （保持稳定以便 E2E 测试断言 + 客户端可读；改时同步通知所有现存客户端）
LEGACY_SUNSET_HEADER = "Tue, 23 Feb 2027 00:00:00 GMT"

from core.data.songs import SongLibrary
from core.data.tabs import MAX_FILE_BYTES
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    SnapshotItemResponse,
    SnapshotListResponse,
    SnapshotRestoreRequest,
    SnapshotRestoreResponse,
)
from server.api.song_models import (
    SongCreateRequest,
    SongDeleteResponse,
    SongEditableFields,
    SongExportResponse,
    SongImportRequest,
    SongImportResult,
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
def api_songs_list(req: Request, status: str = None, include_deleted: bool = False):
    library = _library(get_app_context(req))
    # 触发过期清理（>30 天的真删；幂等）
    library.cleanup_expired()
    songs = library.songs
    # R9.6 默认排除已删除
    if not include_deleted:
        songs = [s for s in songs if not s.deleted_at]
    if status:
        songs = [s for s in songs if s.status == status]
    return {"total": len(songs),
            "active": library.count_active(),
            "draft": library.count_draft(),
            "songs": [_song_dict(s) for s in songs]}


@router.get("/api/songs/trash")
def api_songs_trash(req: Request):
    """R9.6 垃圾桶：列出 deleted_at 距今 ≤ 30 天的歌曲（可恢复或真删）。"""
    library = _library(get_app_context(req))
    library.cleanup_expired()
    deleted = [s for s in library.songs if s.deleted_at]
    # 按 deleted_at 倒序
    deleted.sort(key=lambda s: s.deleted_at, reverse=True)
    return {"total": len(deleted),
            "songs": [_song_dict(s) for s in deleted]}


@router.post("/api/songs/status", response_model=SongLegacyStatusResponse)
def api_songs_status(req: Request, payload: SongLegacyStatusRequest):
    # LEGACY: use PATCH /api/songs/{song_id}/status instead.
    payload = _payload_dict(payload)
    context = get_app_context(req)
    title = (payload.get("title") or "").strip()
    status = (payload.get("status") or "").strip()
    try:
        result = context.song_service.set_status_by_title(title, status)
    except SongServiceError as error:
        return _song_service_error(error)
    return Response(
        content=json.dumps(
            {"ok": True, "title": title, "status": status,
             "active": result.active, "draft": result.draft},
            ensure_ascii=False),
        status_code=200,
        media_type="application/json",
        headers={"Deprecation": "true", "Sunset": LEGACY_SUNSET_HEADER},
    )


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
    # LEGACY: use DELETE /api/songs/{song_id} instead.
    payload = _payload_dict(payload)
    context = get_app_context(req)
    title = (payload.get("title") or "").strip()
    try:
        result = context.song_service.delete_by_title(title)
    except SongServiceError as error:
        return _song_service_error(error)
    return Response(
        content=json.dumps(
            {"ok": True, "title": title,
             "active": result.active, "draft": result.draft},
            ensure_ascii=False),
        status_code=200,
        media_type="application/json",
        headers={"Deprecation": "true", "Sunset": LEGACY_SUNSET_HEADER},
    )


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


# ── L2.3 导入导出（必须在 /api/songs/{song_id} 之前注册） ──

@router.get("/api/songs/export", response_model=SongExportResponse)
def api_songs_export(req: Request):
    """L2.3: 导出整个曲库为 JSON（同 songs.json 格式，含全部 active/draft/trash）。"""
    from datetime import datetime
    context = get_app_context(req)
    library = _library(context)
    songs_data = [asdict(song) for song in library.songs]
    return {
        "schema_version": 2,
        "version": SongLibrary.CURRENT_VERSION,
        "songs": songs_data,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


@router.post("/api/songs/import", response_model=SongImportResult)
def api_songs_import(req: Request, payload: SongImportRequest):
    """L2.3: 批量导入曲库。merge 模式跳过 title 重复；replace 模式覆盖全库。"""
    if payload.mode not in ("merge", "replace"):
        return api_error_response(
            req, 400, ApiError(
                "validation_failed",
                f"未知 mode: {payload.mode}; 仅支持 merge / replace"))
    context = get_app_context(req)
    service = context.song_service
    # 备份（merge 模式保留现有 + 增量；replace 清空后全量覆盖）
    library_snapshot = context.song_repository.load()
    existing_titles = {s.title for s in library_snapshot.value.songs}
    added = 0
    skipped = 0
    errors: list[str] = []
    if payload.mode == "replace":
        # 真删所有现有（不区分软删 / 活动；purge 一次性清空）
        for s in list(library_snapshot.value.songs):
            try:
                service.purge_by_id(s.id)
            except Exception as exc:
                errors.append(f"清空 {s.title} 失败: {exc}")
        existing_titles = set()
    for idx, song_payload in enumerate(payload.songs):
        try:
            title = (song_payload.title or "").strip()
            if not title:
                errors.append(f"第 {idx + 1} 首缺标题")
                skipped += 1
                continue
            if payload.mode == "merge" and title in existing_titles:
                skipped += 1
                continue
            service.create({
                "title": title,
                "artists": song_payload.artists or [],
                "key": song_payload.key or "",
                "capo": song_payload.capo,
                "difficulty": song_payload.difficulty or "",
                "tags": song_payload.tags or [],
                "pinyin": song_payload.pinyin or "",
                "lyrics_lrc": song_payload.lyrics_lrc or "",
                "lyrics_plain": song_payload.lyrics_plain or "",
                "notes": song_payload.notes or "",
                "section": song_payload.section,
                "status": song_payload.status or "draft",
            })
            added += 1
            existing_titles.add(title)
        except Exception as exc:
            errors.append(f"{title or f'#{idx + 1}'}: {exc}")
            skipped += 1
    # 重新统计
    final = context.song_repository.load()
    return {
        "ok": True,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "active": len([s for s in final.value.songs if s.status == "active" and not s.deleted_at]),
        "draft": len([s for s in final.value.songs if s.status == "draft" and not s.deleted_at]),
    }


# ── L2.3 快照（songs.json 每次保存自动备份到 backups/songs/） ──

@router.get("/api/songs/snapshots", response_model=SnapshotListResponse)
def api_songs_snapshots(req: Request):
    """L2.3: 列出 songs.json 的自动快照（按时间倒序）。"""
    from datetime import datetime
    context = get_app_context(req)
    backups_dir = context.paths.backups_dir / "songs"
    if not backups_dir.is_dir():
        return {"total": 0, "items": []}
    items: list[dict] = []
    for path in backups_dir.glob("songs-*.json"):
        try:
            stat = path.stat()
            items.append({
                "filename": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=datetime.now().astimezone().tzinfo
                ).isoformat(timespec="seconds"),
            })
        except OSError:
            continue
    items.sort(key=lambda it: it["modified_at"], reverse=True)
    return {"total": len(items), "items": items}


@router.post("/api/songs/snapshots/restore", response_model=SnapshotRestoreResponse)
def api_songs_snapshots_restore(req: Request, payload: SnapshotRestoreRequest):
    """L2.3: 把指定快照覆盖回 songs.json（从 backups/songs/<filename> 复制）。"""
    from fastapi.responses import JSONResponse
    import shutil
    context = get_app_context(req)
    backup_path = context.paths.backups_dir / "songs" / payload.filename
    if not backup_path.is_file():
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "snapshot_not_found",
                               "message": f"快照不存在：{payload.filename}"}},
        )
    # 直接覆盖 songs.json（repository.save 路径会再次备份当前值；这里直接覆盖是用户意图）
    shutil.copy2(backup_path, context.paths.songs_json)
    return {"ok": True, "filename": payload.filename}


# ── Song ID 主接口 ──

@router.get("/api/songs/{song_id}", response_model=SongResponse)
def api_song_get_by_id(req: Request,
                       song_id: str = Path(..., min_length=1, max_length=128)):
    """按不可变 ID 获取歌曲；新消费者不得再用 title 定位资源。"""
    library = _library(get_app_context(req))
    song = library.get_by_id(song_id)
    if song is None:
        return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
    return _song_dict(song)


@router.patch("/api/songs/{song_id}", response_model=SongUpdateResponse)
def api_song_update_by_id(req: Request,
                          song_id: str = Path(..., min_length=1, max_length=128),
                          payload: SongEditableFields = None):
    """按不可变 ID 更新歌曲，允许修改 title 但禁止修改 id。"""
    context = get_app_context(req)
    payload = _payload_dict(payload)
    try:
        result = context.song_service.update_by_id(song_id, payload)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song": _song_dict(result.song)}


@router.patch("/api/songs/{song_id}/status", response_model=SongMutationResponse)
def api_song_status_by_id(req: Request,
                          song_id: str = Path(..., min_length=1, max_length=128),
                          payload: SongStatusRequest = None):
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
def api_song_delete_by_id(req: Request,
                          song_id: str = Path(..., min_length=1, max_length=128),
                          permanent: bool = False):
    """按不可变 ID 删除歌曲（R9.6 软删除：默认 30 天可恢复；?permanent=true 真删）。"""
    context = get_app_context(req)
    try:
        if permanent:
            result = context.song_service.purge_by_id(song_id)
        else:
            result = context.song_service.delete_by_id(song_id)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song_id": result.song_id,
            "title_snapshot": result.title_snapshot,
            "active": result.active, "draft": result.draft}


@router.post("/api/songs/{song_id}/restore", response_model=SongUpdateResponse)
def api_song_restore_by_id(req: Request,
                           song_id: str = Path(..., min_length=1, max_length=128)):
    """R9.6 恢复软删除的歌曲（清空 deleted_at）。"""
    context = get_app_context(req)
    try:
        song = context.song_service.restore_by_id(song_id)
    except SongServiceError as error:
        return _song_service_error(error)
    return {"ok": True, "song": song}


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
