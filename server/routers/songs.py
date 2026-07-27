"""歌曲管理路由（/api/songs*）。"""
import os
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Request, Response

from server.deps import get_library, get_settings
from core.data.events import append_event
from core.data import tabs as tabs_store
from core.data.songs import Song, pinyin_initials

router = APIRouter()


def _song_dict(s) -> dict:
    return {"title": s.title, "status": s.status, "section": s.section,
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


def _save_library(library, settings):
    from server.deps import ROOT, SONGS_JSON
    backup_dir = os.path.join(ROOT, "data", "backups")
    library.save(SONGS_JSON, backup_dir=backup_dir,
                 backup_count=settings.get("backup_count", 20))


def _events_path():
    from server.deps import EVENTS_JSONL
    return EVENTS_JSONL


@router.get("/api/songs")
def api_songs(req: Request):
    library = get_library(req.app.state)
    from server.deps import _count_by_len
    return {"total": len(library.mastered()),
            "by_len": _count_by_len(library)}


@router.get("/api/songs/list")
def api_songs_list(req: Request, status: str = None):
    library = get_library(req.app.state)
    songs = library.songs
    if status:
        songs = [s for s in songs if s.status == status]
    return {"total": len(songs),
            "active": library.count_active(),
            "draft": library.count_draft(),
            "songs": [_song_dict(s) for s in songs]}


@router.post("/api/songs/status")
def api_songs_status(req: Request, payload: dict):
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
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
    _save_library(library, settings)
    append_event(_events_path(), "song_learned" if status == "active" else "song_unlearned",
                 title=title)
    return {"ok": True, "title": title, "status": status,
            "active": library.count_active(), "draft": library.count_draft()}


@router.post("/api/songs/update")
def api_songs_update(req: Request, payload: dict):
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
    title = (payload.get("title") or "").strip()
    try:
        fields = _clean_song_fields(payload.get("fields") or {})
        if not fields:
            return Response("fields 为空", status_code=400)
        old_song = library.get(title)
        old_view = _song_dict(old_song) if old_song else None
        ok = library.update(title, fields)
    except ValueError as e:
        return Response(str(e), status_code=400)
    if not ok:
        return Response(f"未找到歌曲：{title}", status_code=404)
    _save_library(library, settings)
    song = library.get(fields.get("title", title))
    changes = [{"field": k, "old": old_view.get(k), "new": song and _song_dict(song).get(k)}
               for k in fields if old_view and old_view.get(k) != _song_dict(song).get(k)]
    append_event(_events_path(), "song_edited", title=song.title,
                 meta={"changes": changes})
    return {"ok": True, "song": _song_dict(song)}


@router.post("/api/songs/add")
def api_songs_add(req: Request, payload: dict):
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
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
    _save_library(library, settings)
    append_event(_events_path(), "song_added", title=title, meta={"status": song.status})
    return {"ok": True, "song": _song_dict(song),
            "active": library.count_active(), "draft": library.count_draft()}


@router.post("/api/songs/delete")
def api_songs_delete(req: Request, payload: dict):
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
    title = (payload.get("title") or "").strip()
    if not library.remove(title):
        return Response(f"未找到歌曲：{title}", status_code=404)
    _save_library(library, settings)
    append_event(_events_path(), "song_deleted", title=title)
    return {"ok": True, "title": title,
            "active": library.count_active(), "draft": library.count_draft()}


# ── 曲谱附件 ──

@router.post("/api/songs/{title}/tabs")
async def api_tab_upload(req: Request, title: str, file: UploadFile = File(...)):
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
    from server.deps import TABS_DIR
    song = library.get(title)
    if song is None:
        return Response(f"未找到歌曲：{title}", status_code=404)
    data = await file.read()
    try:
        rel = tabs_store.save_tab(TABS_DIR, title, file.filename or "tab.png", data)
    except ValueError as e:
        return Response(str(e), status_code=400)
    song.tab_files.append(rel)
    _save_library(library, settings)
    append_event(_events_path(), "song_edited", title=title,
                 meta={"changes": [{"field": "tab_files", "old": None, "new": rel}]})
    return {"ok": True, "file": rel, "tab_files": song.tab_files}


@router.get("/api/songs/{title}/tabs")
def api_tab_list(req: Request, title: str):
    library = get_library(req.app.state)
    song = library.get(title)
    if song is None:
        return Response(f"未找到歌曲：{title}", status_code=404)
    return {"title": title, "tab_files": song.tab_files}


@router.delete("/api/songs/{title}/tabs")
def api_tab_delete(req: Request, title: str, file: str):
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
    from server.deps import TABS_DIR
    song = library.get(title)
    if song is None:
        return Response(f"未找到歌曲：{title}", status_code=404)
    if file not in song.tab_files:
        return Response(f"曲谱不存在：{file}", status_code=404)
    song.tab_files.remove(file)
    tabs_store.delete_tab(TABS_DIR, title, file)
    _save_library(library, settings)
    append_event(_events_path(), "song_edited", title=title,
                 meta={"changes": [{"field": "tab_files", "old": file, "new": None}]})
    return {"ok": True, "tab_files": song.tab_files}
