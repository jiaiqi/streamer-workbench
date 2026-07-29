"""歌曲管理路由（/api/songs*）。"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Response

from server.dependencies import get_app_context
from server.ports.repositories import RepositoryConflict, RepositoryError
from core.data.events import append_event, _normalize_timestamp
from core.data import tabs as tabs_store
from core.data.songs import Song, pinyin_initials

router = APIRouter()


def _song_dict(s) -> dict:
    return {"id": s.id, "title": s.title, "status": s.status, "section": s.section,
            "artists": s.artists, "lyricist": s.lyricist, "composer": s.composer,
            "key": s.key, "capo": s.capo, "difficulty": s.difficulty,
            "tabs": s.tabs, "tags": s.tags, "pinyin": s.pinyin,
            "added_at": s.added_at, "notes": s.notes,
            "learned_at": s.learned_at, "tab_files": s.tab_files}


def _clean_song_fields(payload: dict) -> dict:
    from core.data.songs import SongLibrary
    fields = {}
    for k in SongLibrary.EDITABLE_FIELDS:
        if k not in payload:
            continue
        v = payload[k]
        if k in ("artists", "tags"):
            fields[k] = [str(x).strip() for x in (v or []) if str(x).strip()]
        elif k == "capo":
            fields[k] = None if v in (None, "") else max(0, min(12, int(v)))
        elif k == "section":
            fields[k] = None if v in (None, "") else max(1, min(7, int(v)))
        else:
            fields[k] = str(v).strip() if v is not None else ""
    if "title" in fields and not fields["title"]:
        raise ValueError("歌名不能为空")
    return fields


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


@router.get("/api/songs")
def api_songs(req: Request):
    library = _library(get_app_context(req))
    from server.deps import _count_by_len
    return {"total": len(library.mastered()),
            "by_len": _count_by_len(library)}


@router.get("/api/songs/list")
def api_songs_list(req: Request, status: str = None):
    library = _library(get_app_context(req))
    songs = library.songs
    if status:
        songs = [s for s in songs if s.status == status]
    return {"total": len(songs),
            "active": library.count_active(),
            "draft": library.count_draft(),
            "songs": [_song_dict(s) for s in songs]}


@router.post("/api/songs/status")
def api_songs_status(req: Request, payload: dict):
    context = get_app_context(req)
    library = _library(context)
    title = (payload.get("title") or "").strip()
    status = (payload.get("status") or "").strip()
    if status not in ("active", "draft"):
        return Response("status 必须是 active 或 draft", status_code=400)
    mark = library.mark_active if status == "active" else library.mark_draft
    if not mark(title):
        return Response(f"未找到歌曲：{title}", status_code=404)
    if status == "active":
        song = library.get(title)
        if song is not None:
            song.learned_at = datetime.now().strftime("%Y-%m-%d")
    else:
        song = library.get(title)
    _save_library(context, library)
    _append_event(context, "song_learned" if status == "active" else "song_unlearned",
                 song_id=song.id if song else None, title_snapshot=title,
                 source="songs-api")
    return {"ok": True, "title": title, "status": status,
            "active": library.count_active(), "draft": library.count_draft()}


@router.post("/api/songs/update")
def api_songs_update(req: Request, payload: dict):
    context = get_app_context(req)
    library = _library(context)
    title = (payload.get("title") or "").strip()
    try:
        fields = _clean_song_fields(payload.get("fields") or {})
        if not fields:
            return Response("fields 为空", status_code=400)
        old_song = library.get(title)
        old_view = _song_dict(old_song) if old_song else None
        ok = library.update(title, fields)
    except ValueError as e:
        status_code = 409 if "改名失败" in str(e) else 400
        return Response(str(e), status_code=status_code)
    if not ok:
        return Response(f"未找到歌曲：{title}", status_code=404)
    _save_library(context, library)
    song = library.get(fields.get("title", title))
    changes = [{"field": k, "old": old_view.get(k), "new": song and _song_dict(song).get(k)}
               for k in fields if old_view and old_view.get(k) != _song_dict(song).get(k)]
    _append_event(context, "song_edited", song_id=song.id,
                 title_snapshot=song.title, meta={"changes": changes},
                 source="songs-api")
    return {"ok": True, "song": _song_dict(song)}


@router.post("/api/songs/add")
def api_songs_add(req: Request, payload: dict):
    context = get_app_context(req)
    library = _library(context)
    try:
        fields = _clean_song_fields(payload)
    except (ValueError, TypeError) as e:
        return Response(str(e), status_code=400)
    title = fields.pop("title", "")
    if not title:
        return Response("歌名不能为空", status_code=400)
    song = Song(title=title,
                status=payload.get("status") if payload.get("status") in ("active", "draft") else "draft",
                added_at=datetime.now().strftime("%Y-%m-%d"),
                **fields)
    if not song.pinyin:
        song.pinyin = pinyin_initials(title)
    if not library.add(song):
        return Response(f"歌曲已存在：{title}", status_code=409)
    _save_library(context, library)
    _append_event(context, "song_added", song_id=song.id,
                 title_snapshot=title, meta={"status": song.status},
                 source="songs-api")
    return {"ok": True, "song": _song_dict(song),
            "active": library.count_active(), "draft": library.count_draft()}


@router.post("/api/songs/delete")
def api_songs_delete(req: Request, payload: dict):
    context = get_app_context(req)
    library = _library(context)
    title = (payload.get("title") or "").strip()
    song = library.get(title)
    if song is None or not library.remove(title):
        return Response(f"未找到歌曲：{title}", status_code=404)
    _save_library(context, library)
    _append_event(context, "song_deleted", song_id=song.id,
                 title_snapshot=title, source="songs-api")
    return {"ok": True, "title": title,
            "active": library.count_active(), "draft": library.count_draft()}


# ── Song ID 主接口 ──

@router.get("/api/songs/{song_id}")
def api_song_get_by_id(req: Request, song_id: str):
    """按不可变 ID 获取歌曲；新消费者不得再用 title 定位资源。"""
    library = _library(get_app_context(req))
    song = library.get_by_id(song_id)
    if song is None:
        return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
    return _song_dict(song)


@router.patch("/api/songs/{song_id}")
def api_song_update_by_id(req: Request, song_id: str, payload: dict):
    """按不可变 ID 更新歌曲，允许修改 title 但禁止修改 id。"""
    context = get_app_context(req)
    library = _library(context)
    song = library.get_by_id(song_id)
    if song is None:
        return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
    old_view = _song_dict(song)
    try:
        fields = _clean_song_fields(payload)
        if not fields:
            return Response("fields 为空", status_code=400)
        library.update_by_id(song_id, fields)
    except ValueError as e:
        status_code = 409 if "改名失败" in str(e) else 400
        return Response(str(e), status_code=status_code)
    _save_library(context, library)
    current = library.get_by_id(song_id)
    current_view = _song_dict(current)
    changes = [{"field": key, "old": old_view.get(key), "new": current_view.get(key)}
               for key in fields if old_view.get(key) != current_view.get(key)]
    _append_event(context, "song_edited", song_id=current.id,
                 title_snapshot=current.title, meta={"changes": changes},
                 source="songs-api")
    return {"ok": True, "song": current_view}


@router.patch("/api/songs/{song_id}/status")
def api_song_status_by_id(req: Request, song_id: str, payload: dict):
    """按不可变 ID 修改 active/draft 状态。"""
    context = get_app_context(req)
    library = _library(context)
    status = (payload.get("status") or "").strip()
    if status not in ("active", "draft"):
        return Response("status 必须是 active 或 draft", status_code=400)
    song = library.get_by_id(song_id)
    if song is None:
        return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
    mark = library.mark_active_by_id if status == "active" else library.mark_draft_by_id
    mark(song_id)
    if status == "active":
        song.learned_at = datetime.now().strftime("%Y-%m-%d")
    _save_library(context, library)
    _append_event(context, "song_learned" if status == "active" else "song_unlearned",
                 song_id=song.id, title_snapshot=song.title, source="songs-api")
    return {"ok": True, "song": _song_dict(song),
            "active": library.count_active(), "draft": library.count_draft()}


@router.delete("/api/songs/{song_id}")
def api_song_delete_by_id(req: Request, song_id: str):
    """按不可变 ID 删除歌曲；历史事件保留 ID 与 title_snapshot。"""
    context = get_app_context(req)
    library = _library(context)
    song = library.get_by_id(song_id)
    if song is None:
        return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
    library.remove_by_id(song_id)
    _save_library(context, library)
    _append_event(context, "song_deleted", song_id=song.id,
                 title_snapshot=song.title, source="songs-api")
    return {"ok": True, "song_id": song.id, "title_snapshot": song.title,
            "active": library.count_active(), "draft": library.count_draft()}


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
