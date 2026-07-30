"""渲染/主题/布局路由（/api/render, /api/themes, /api/thumb, /api/layouts）。"""
import io
import os
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from PIL import Image

from server.dependencies import get_app_context
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import RenderRequest
from core.spec import get_canvas_spec
from core.layouts import get_layout, list_layouts, layout_params
from server.api.secondary_models import RenderDocumentRequest, RenderDocumentResponse
from server.services.posters import (
    PosterNotFound,
    PosterServiceError,
    PosterValidationFailed,
)
from server.services.render_document import build_render_document, render_document

router = APIRouter()


@router.get("/api/themes")
def api_themes(req: Request):
    themes = get_app_context(req).themes
    return [{"name": t.name, "prefix": t.output_prefix,
             "watermark_fix": t.watermark_fix,
             "backgrounds": t.backgrounds,
             "notes": t.notes} for t in themes.values()]


@router.get("/api/thumb/{theme_name}")
def api_thumb(theme_name: str, req: Request):
    context = get_app_context(req)
    themes = context.themes
    cache = req.app.state.thumb_cache
    if theme_name in cache:
        return Response(content=cache[theme_name], media_type="image/jpeg")
    t = themes.get(theme_name)
    if t is None:
        return Response("主题不存在", status_code=404)
    bg = t.backgrounds.get("1")
    path = os.path.join(context.paths.themes_dir, theme_name, bg) if bg else ""
    if not bg or not os.path.isfile(path):
        return Response("背景不存在", status_code=404)
    im = Image.open(path).convert("RGB")
    im.thumbnail((360, 1080))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    data = buf.getvalue()
    cache[theme_name] = data
    return Response(content=data, media_type="image/jpeg")


@router.get("/api/layouts")
def api_layouts():
    return list_layouts()


@router.get("/api/layouts/{layout_id}/params")
def api_layout_params(layout_id: str):
    try:
        return layout_params(layout_id)
    except KeyError as e:
        return Response(str(e), status_code=404)


@router.get("/api/layouts/{layout_id}/capabilities")
def api_layout_capabilities(layout_id: str, req: Request):
    """P1 R1a.3：单布局能力声明，UI 据此过滤主题/比例/分类组合。

    仅 P1 范围：grid-wrap。
    """
    try:
        plugin = get_layout(layout_id)
    except KeyError as e:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(e)),
        )
    caps = plugin.capabilities()
    if hasattr(plugin, "estimate_capacity"):
        caps["capacity"] = plugin.estimate_capacity("9:20")
    caps["id"] = layout_id
    return caps


@router.get("/api/render", response_class=Response,
            responses={200: {"content": {"image/png": {}}}})
def api_render(req: Request, query: Annotated[RenderRequest, Query()]):
    theme, page = query.theme, query.page
    canvas, avoid, layout = query.canvas, query.avoid, query.layout
    margin, font_song = query.margin, query.font_song
    row_h, sec_gap = query.row_h, query.sec_gap
    context = get_app_context(req)
    themes = context.themes
    songs = context.song_repository.load()
    font = str(context.paths.fonts_dir / "MaokenAssortedSans.ttf")
    if theme not in themes:
        return api_error_response(
            req, 404, ApiError("theme_not_found", f"未知主题：{theme}"))
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(e)))
    spec = get_canvas_spec(canvas, avoid=avoid)
    overrides = {k: v for k, v in
                 {"margin": margin, "font_song": font_song,
                  "row_h": row_h, "sec_gap": sec_gap}.items()
                 if v is not None}
    if overrides:
        spec = replace(spec, **overrides)
    # P1 R1a.3 超容量检查：grid-wrap 固定 2 页，超容量明确返回错误而非静默丢歌
    if hasattr(layout_plugin, "check_overflow"):
        overflow, reason = layout_plugin.check_overflow(songs.value, spec)
        if overflow:
            return api_error_response(
                req, 400,
                ApiError("layout_overflow",
                         f"歌曲超出 grid-wrap 容量：{reason}"),
            )
    document = build_render_document(
        song_snapshot=songs, theme=themes[theme], layout_id=layout_plugin.id,
        canvas=spec, page=page, font_path=font, parameters=overrides)
    img = render_document(document)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@router.post("/api/render/document",
            response_model=RenderDocumentResponse)
def api_render_document(req: Request, payload: RenderDocumentRequest):
    """P1 R1a.4：海报渲染预览 - 通过 poster_id 解析 SongSource,
    构造不可变 RenderDocument, 返回 JSON 描述与 document_id。

    配套：相同 document_id 可由 /api/render/document/image 触发实际渲染 PNG。
    """
    context = get_app_context(req)
    themes = context.themes
    if payload.theme_id not in themes:
        return api_error_response(
            req, 404, ApiError("theme_not_found", f"未知主题：{payload.theme_id}"))
    try:
        layout_plugin = get_layout(payload.layout_id)
    except KeyError as e:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(e)))
    # 解析 SongSource 到具体 Song 列表
    try:
        poster, full_library, poster_library, missing = (
            context.poster_service.resolve_for_render(payload.poster_id)
        )
    except PosterNotFound as e:
        return api_error_response(
            req, 404, ApiError("poster_not_found", str(e)))
    except PosterValidationFailed as e:
        return api_error_response(
            req, 400, ApiError("invalid_poster", str(e)))
    except PosterServiceError as e:
        return api_error_response(
            req, 500, ApiError("poster_error", str(e)))
    # canvas spec
    spec = get_canvas_spec(payload.canvas_id, avoid=True)
    # P1 R1a.3 超容量检查（按 PosterDocument 解析后的子集）
    if hasattr(layout_plugin, "check_overflow"):
        overflow, reason = layout_plugin.check_overflow(poster_library, spec)
        if overflow:
            return api_error_response(
                req, 400,
                ApiError("layout_overflow",
                         f"海报「{poster.name}」超容量：{reason}"),
            )
    font = str(context.paths.fonts_dir / "MaokenAssortedSans.ttf")
    # build_render_document 需要 StoredSnapshot[SongLibrary]
    from server.ports.repositories import StoredSnapshot
    snapshot = StoredSnapshot(value=poster_library,
                              revision=context.song_repository.load().revision)
    document = build_render_document(
        song_snapshot=snapshot,
        theme=themes[payload.theme_id],
        layout_id=layout_plugin.id,
        canvas=spec, page=payload.page,
        font_path=font,
        title=poster.name,
        subtitle="",
        parameters=payload.parameters,
    )
    # 响应：document + metadata；document_id 是不可变输入 hash
    return {
        "document_id": document.document_id,
        "poster_id": payload.poster_id,
        "layout_id": payload.layout_id,
        "theme_id": payload.theme_id,
        "canvas_id": payload.canvas_id,
        "page": payload.page,
        "pages_total": layout_plugin.pages or 1,
        "song_count": len(document.song_snapshots),
        "missing_song_ids": missing,
        "page_policy_mode": poster.page_policy.mode,
        "document": {
            "document_id": document.document_id,
            "page_policy": document.page_policy,
            "engine_version": document.engine_version,
            "source_revisions": {
                "songs": document.source_revisions.songs,
                "settings": document.source_revisions.settings,
                "theme": document.source_revisions.theme,
            },
        },
    }


@router.post("/api/render/document/image",
            response_class=Response,
            responses={200: {"content": {"image/png": {}}}})
def api_render_document_image(req: Request, payload: RenderDocumentRequest):
    """根据 RenderDocument 端点构造的同一输入, 渲染并返回 PNG。"""
    # 与 api_render_document 共享 RenderDocument 构造路径 (preview == export)
    context = get_app_context(req)
    themes = context.themes
    if payload.theme_id not in themes:
        return api_error_response(
            req, 404, ApiError("theme_not_found", f"未知主题：{payload.theme_id}"))
    try:
        layout_plugin = get_layout(payload.layout_id)
    except KeyError as e:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(e)))
    try:
        poster, _, poster_library, _ = (
            context.poster_service.resolve_for_render(payload.poster_id)
        )
    except PosterNotFound as e:
        return api_error_response(
            req, 404, ApiError("poster_not_found", str(e)))
    except (PosterValidationFailed, PosterServiceError) as e:
        return api_error_response(
            req, 400 if isinstance(e, PosterValidationFailed) else 500,
            ApiError("poster_error", str(e)))
    spec = get_canvas_spec(payload.canvas_id, avoid=True)
    if hasattr(layout_plugin, "check_overflow"):
        overflow, reason = layout_plugin.check_overflow(poster_library, spec)
        if overflow:
            return api_error_response(
                req, 400,
                ApiError("layout_overflow",
                         f"海报「{poster.name}」超容量：{reason}"),
            )
    font = str(context.paths.fonts_dir / "MaokenAssortedSans.ttf")
    from server.ports.repositories import StoredSnapshot
    snapshot = StoredSnapshot(value=poster_library,
                              revision=context.song_repository.load().revision)
    document = build_render_document(
        song_snapshot=snapshot,
        theme=themes[payload.theme_id],
        layout_id=layout_plugin.id,
        canvas=spec, page=payload.page,
        font_path=font,
        title=poster.name,
        subtitle="",
        parameters=payload.parameters,
    )
    img = render_document(document)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")
