"""渲染/主题/布局路由（/api/render, /api/themes, /api/thumb, /api/layouts）。"""
import io
import os
from dataclasses import replace

from fastapi import APIRouter, Request, Response
from PIL import Image

from server.dependencies import get_app_context
from core.spec import get_canvas_spec
from core.layouts import get_layout, list_layouts, layout_params
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


@router.get("/api/render")
def api_render(req: Request,
               theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    context = get_app_context(req)
    themes = context.themes
    songs = context.song_repository.load()
    font = str(context.paths.fonts_dir / "MaokenAssortedSans.ttf")
    if theme not in themes:
        return Response(f"未知主题：{theme}", status_code=404)
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    spec = get_canvas_spec(canvas, avoid=avoid)
    overrides = {k: v for k, v in
                 {"margin": margin, "font_song": font_song,
                  "row_h": row_h, "sec_gap": sec_gap}.items()
                 if v is not None}
    if overrides:
        spec = replace(spec, **overrides)
    document = build_render_document(
        song_snapshot=songs, theme=themes[theme], layout_id=layout_plugin.id,
        canvas=spec, page=page, font_path=font, parameters=overrides)
    img = render_document(document)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")
