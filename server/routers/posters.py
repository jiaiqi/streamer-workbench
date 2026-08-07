"""R1a.1 Poster HTTP 适配层（/api/posters*）。

路由表：
- GET    /api/posters              列出已保存海报摘要
- POST   /api/posters              创建或覆盖更新（id 缺则生成）
- GET    /api/posters/{id}         读取完整 PosterDocument
- DELETE /api/posters/{id}         软删除
- POST   /api/posters/{id}/resolve 解析 SongSource → 歌曲快照列表
- GET    /api/posters/{id}/thumb   200x200 缩略图（后端懒生成；P0 UX）
- PATCH  /api/posters/{id}/name    inline 重命名
- POST   /api/posters/{id}/duplicate 复制（生成新 id + "(副本)" 名称）

并发写由 expected_revision CAS 在 service 层处理；HTTP 层只做翻译。
"""
from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Request, Response

from core.data.posters import PosterDocument
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    NamePatchRequest,
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


# ── M3 海报 UI/UX（P0 缩略图 + 重命名 + 复制） ──────────────────────────

THUMB_SIZE = (200, 200)
THUMB_QUALITY = 85  # JPEG 质量（如果用 JPEG；当前 PIL PNG 不需要）


def _thumb_path(paths, poster_id: str) -> Path:
    """缩略图缓存路径：data/posters/{id}/.thumb.png。"""
    return paths.posters_dir / poster_id / ".thumb.png"


def _generate_thumb(req: Request, poster_id: str) -> bytes:
    """懒生成 200x200 缩略图并落盘；返回 PNG bytes。"""
    context = get_app_context(req)
    try:
        poster, _ = context.poster_service.get_with_revision(poster_id)
    except PosterServiceError as error:
        raise error
    # 解析 SongSource → snapshot
    try:
        _poster, _full_lib, poster_lib, _missing = (
            context.poster_service.resolve_for_render(poster_id))
    except PosterServiceError as error:
        raise error
    # 选主题：取 layout_id 默认（grid-wrap 用第一个 theme 作 fallback）
    themes = context.themes
    # 取 poster 自己声明的主题；如果解析失败用第一个
    theme_id = poster.theme_id or (next(iter(themes)) if themes else None)
    if not theme_id or theme_id not in themes:
        if themes:
            theme_id = next(iter(themes))
        else:
            return b""
    theme = themes[theme_id]
    # 选 layout
    from core.layouts import get_layout
    try:
        layout = get_layout(poster.layout_id)
    except KeyError:
        layout = get_layout("grid-wrap")
    # 渲染第一页（render_page 接受 SongLibrary 本身）
    from core.engine import render_page
    from core.spec import get_canvas_spec
    from PIL import Image as _PILImage
    spec = get_canvas_spec("抖音全屏 9:20", avoid=True)
    img = render_page(theme, layout, poster_lib, spec, page=1,
                      font_path=str(context.paths.fonts_dir / "MaokenAssortedSans.ttf"))
    # 等比缩放到 200x200（cover 模式：填满 + 中心裁剪）
    img.thumbnail(THUMB_SIZE, _PILImage.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@router.get(
    "/api/posters/{poster_id}/thumb",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def api_poster_thumb(poster_id: str, req: Request):
    """返回 200x200 缩略图（PNG）。首次请求懒生成；命中缓存直接读。

    缓存策略：
    - 路径 data/posters/{id}/.thumb.png
    - 若文件存在且 mtime 比 data/posters/{id}/poster.json 新 → 命中
    - 否则重新生成（覆盖旧文件）
    """
    from PIL import Image
    context = get_app_context(req)
    paths = context.paths
    thumb = _thumb_path(paths, poster_id)
    poster_json = paths.posters_dir / poster_id / "poster.json"
    # 缓存命中：thumb 存在 + 不比 poster.json 旧
    if thumb.exists() and poster_json.exists() and thumb.stat().st_mtime >= poster_json.stat().st_mtime:
        return Response(thumb.read_bytes(), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    # 缓存失效或不存在：重新生成
    try:
        png_bytes = _generate_thumb(req, poster_id)
    except PosterNotFound as error:
        return _service_error(req, error)
    except Exception as error:
        return api_error_response(
            req, 500,
            ApiError("thumb_generate_failed", f"缩略图生成失败: {error}"))
    if not png_bytes:
        return api_error_response(
            req, 500,
            ApiError("thumb_generate_failed", "无可用主题渲染缩略图"))
    # 落盘缓存（如果目录不存在则跳过缓存但仍返回）
    try:
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(png_bytes)
    except OSError:
        # 缓存写入失败（只读盘？）不阻塞响应
        pass
    return Response(png_bytes, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.patch("/api/posters/{poster_id}/name", response_model=OkResponse)
def api_poster_rename(poster_id: str, payload: NamePatchRequest, req: Request):
    """inline 重命名：仅修改 name 字段，不动其他内容。

    用 expected_revision CAS 防并发覆盖；客户端必须先 GET 拿当前 revision。
    """
    try:
        context = get_app_context(req)
        poster, revision = context.poster_service.get_with_revision(poster_id)
        # 构造新 document（仅 name 改）
        new_payload = poster.to_dict()
        new_payload["name"] = payload.name
        if payload.revision is not None:
            new_payload["revision"] = payload.revision
        result = context.poster_service.save(new_payload)
        # 失效缩略图缓存（虽然 thumb 是按 poster.json mtime 触发，但 rename 不会改 mtime）
        # 实际上重命名不应失效缩略图，skip
    except PosterServiceError as error:
        return _service_error(req, error)
    return {"ok": True, "id": result.poster.id,
            "revision": result.revision, "name": result.poster.name}


@router.post(
    "/api/posters/{poster_id}/duplicate",
    response_model=PosterSaveResponse,
)
def api_poster_duplicate(poster_id: str, req: Request):
    """复制当前海报：生成新 id + name 追加「(副本)」。"""
    try:
        context = get_app_context(req)
        poster, _ = context.poster_service.get_with_revision(poster_id)
        new_payload = poster.to_dict()
        # 移除 id 让 service 生成新 id
        new_payload.pop("id", None)
        new_payload["revision"] = None
        new_payload["name"] = f"{poster.name}（副本）"
        result = context.poster_service.save(new_payload)
    except PosterServiceError as error:
        return _service_error(req, error)
    return {
        "ok": True,
        "id": result.poster.id,
        "revision": result.revision,
        "updated_at": result.poster.updated_at,
    }

