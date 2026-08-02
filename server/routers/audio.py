"""R8.1 弹唱：音频附件 HTTP 路由（/api/songs/{id}/audio* + /api/playback/events）。

端点：
- POST   /api/songs/{identity}/audio     上传音频（multipart: file + role）
- GET    /api/songs/{identity}/audio/list 列出该歌的所有音频
- DELETE /api/songs/{identity}/audio?role=vocal 删除指定 role
- GET    /api/songs/{identity}/audio/{role}  流式服务音频文件（FileResponse）
- POST   /api/playback/events     上报播放事件（playback_started/paused/completed）

设计
----
- 复用 core/audio.py 的 save_audio / delete_audio / list_audio
- 复用 events.jsonl 事件管道（type=playback_*）
- identity 支持 song_id（song_xxxx）或旧 title（按 SongService 现状）
- 错误统一走 ApiError + api_error_response
- 流式用 FileResponse（先不支持 Range；HTML5 audio 会自动缓冲；v8.x 视情况加）
"""
from __future__ import annotations

import io
import os
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    AudioListResponse,
    AudioStreamInfo,
    AudioUploadResponse,
    PlaybackEventRequest,
    PlaybackEventResponse,
)
from server.dependencies import get_app_context


router = APIRouter()

# 与 core/audio.py 对齐
_ALLOWED_EXT = {".mp3", ".m4a", ".ogg", ".wav", ".webm"}
_AUDIO_ROLES = ("vocal", "instrumental")
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50MB

# MIME type 映射（流式 Content-Type 用）
_MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}

# playback 事件类型白名单
_PLAYBACK_EVENT_TYPES = {"playback_started", "playback_paused", "playback_completed"}


# ── 上传 / 列出 / 删除 / 流式 ──


@router.post("/api/songs/{identity}/audio", response_model=AudioUploadResponse)
async def api_audio_upload(
    req: Request,
    identity: str,
    file: UploadFile = File(...),
    role: Annotated[str, Query(description="vocal | instrumental")] = "vocal",
):
    """R8.1: 上传音频到 data/audio/{song_id}/vocal.{ext} 或 instrumental.{ext}。

    复用 core/audio.save_audio 路径白名单 + 大小校验。
    同时回写 Song.audio_vocal_path / Song.audio_instrumental_path。
    """
    if role not in _AUDIO_ROLES:
        return api_error_response(
            req, 400, ApiError(
                "invalid_audio_role",
                f"不支持的 audio role：{role!r}（仅 {_AUDIO_ROLES}）",
            ))

    data = await file.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        return api_error_response(
            req, 413, ApiError(
                "audio_too_large",
                f"音频超过 {_MAX_FILE_BYTES // 1024 // 1024}MB 上限",
            ))

    ctx = get_app_context(req)
    try:
        song = ctx.song_service.resolve_audio_upload(
            identity, role, file.filename or "audio.mp3", data)
    except ValueError as exc:
        # core/audio.save_audio 抛 ValueError：扩展名不支持 / 文件超 50MB
        msg = str(exc)
        if "超过" in msg or "MB" in msg:
            code, status = "audio_too_large", 413
        else:
            code, status = "invalid_audio_format", 400
        return api_error_response(req, status, ApiError(code, msg))
    except Exception as exc:
        # 404 (SongNotFound) 透传 — 业务错误保持语义
        msg = str(exc)
        if "未找到" in msg:
            return api_error_response(req, 404, ApiError("song_not_found", msg))
        raise  # 其他错误让上层处理
    return {
        "ok": True,
        "song_id": song.id,
        "role": role,
        "filename": os.path.basename(song.audio_vocal_path if role == "vocal" else song.audio_instrumental_path),
        "path": song.audio_vocal_path if role == "vocal" else song.audio_instrumental_path,
    }


@router.get("/api/songs/{identity}/audio/list", response_model=AudioListResponse)
def api_audio_list(req: Request, identity: str):
    """列出该歌的所有音频文件。"""
    ctx = get_app_context(req)
    items = ctx.song_service.list_audio(identity)
    return {"song_id": ctx.song_service.resolve_id(identity), "items": items}


@router.delete("/api/songs/{identity}/audio", response_model=AudioListResponse)
def api_audio_delete(
    req: Request,
    identity: str,
    role: Annotated[str, Query(description="vocal | instrumental")] = ...,
):
    """删除指定 role 的音频（保留另一个 role）。"""
    if role not in _AUDIO_ROLES:
        return api_error_response(
            req, 400, ApiError(
                "invalid_audio_role",
                f"不支持的 audio role：{role!r}（仅 {_AUDIO_ROLES}）",
            ))
    ctx = get_app_context(req)
    items = ctx.song_service.delete_audio(identity, role)
    return {"song_id": ctx.song_service.resolve_id(identity), "items": items}


@router.get("/api/songs/{identity}/audio/{role}", response_model=AudioStreamInfo)
def api_audio_info(
    req: Request,
    identity: str,
    role: str,
):
    """音频文件元信息（HEAD 也走这里）。"""
    if role not in _AUDIO_ROLES:
        return api_error_response(
            req, 400, ApiError("invalid_audio_role", f"不支持的 role：{role!r}"))
    ctx = get_app_context(req)
    info = ctx.song_service.audio_info(identity, role)
    if info is None:
        return api_error_response(
            req, 404, ApiError("audio_not_found", f"{identity} 没有 {role} 音频"))
    return info


# FileResponse 走的是独立路径（GET /audio/{role} 文件流）
@router.get("/api/songs/{identity}/audio/{role}/file")
def api_audio_stream(req: Request, identity: str, role: str):
    """流式服务音频文件（HTML5 audio src 直接用）。"""
    if role not in _AUDIO_ROLES:
        return api_error_response(
            req, 400, ApiError("invalid_audio_role", f"不支持的 role：{role!r}"))
    ctx = get_app_context(req)
    abs_path = ctx.song_service.audio_abs_path(identity, role)
    if abs_path is None:
        return api_error_response(
            req, 404, ApiError("audio_not_found", f"{identity} 没有 {role} 音频"))
    # MIME 推断
    ext = os.path.splitext(abs_path)[1].lower()
    media_type = _MIME_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(
        abs_path,
        media_type=media_type,
        filename=os.path.basename(abs_path),
        headers={"Accept-Ranges": "bytes"},  # 声明支持 Range（实际由静态服务承担）
    )


# ── 播放事件上报 ──


@router.post("/api/playback/events", response_model=PlaybackEventResponse)
def api_playback_event(req: Request, payload: PlaybackEventRequest):
    """R8.1: 上报播放事件（playback_started / paused / completed）。

    写入 events.jsonl（schema_version=2，复用 EventStore.append）。
    """
    if payload.type not in _PLAYBACK_EVENT_TYPES:
        return api_error_response(
            req, 400, ApiError(
                "invalid_playback_event",
                f"不支持的 event type：{payload.type!r}（仅 {sorted(_PLAYBACK_EVENT_TYPES)}）",
            ))
    ctx = get_app_context(req)
    ctx.event_store.append({
        "schema_version": 2,
        "event_id": f"evt_{__import__('uuid').uuid4().hex}",
        "occurred_at": payload.occurred_at
            or __import__('datetime').datetime.now().astimezone().isoformat(timespec="seconds"),
        "recorded_at": __import__('datetime').datetime.now().astimezone().isoformat(timespec="seconds"),
        "type": payload.type,
        "source": "player-ui",
        "meta": {
            "kind": payload.type,  # R4.2.3 对齐：用 kind 字段而非 source 推断
            "song_id": payload.song_id,
            "source": payload.source,         # "vocal" | "instrumental" | None
            "position_ms": payload.position_ms,
            "duration_ms": payload.duration_ms,
        },
    })
    return {"ok": True, "type": payload.type}
