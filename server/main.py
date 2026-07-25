"""本地渲染后端（开发期）。

FastAPI 暴露渲染/主题/歌曲接口。前端（浏览器或后期 Electron BrowserWindow）连
http://localhost:8000 调用。MVP 后期由 Electron 把本服务打包为 child_process。

运行（项目根目录下）：
    pip install -r requirements.txt
    uvicorn server.main:app --reload --port 8000
"""

import io
import os
from dataclasses import replace

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.spec import CANVAS_PRESETS
from core.themes.loader import load_themes
from core.layouts import get_layout, list_layouts, layout_params
from core.data.songs import build_default_library
from core.engine import render_page

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT, "themes")
FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")

app = FastAPI(title="歌单海报生成器 · 渲染后端")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 开发期放开；生产期收窄到 Electron 域名
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/bg", StaticFiles(directory=THEMES_DIR), name="theme_bg")

SONGS_JSON = os.path.join(ROOT, "data", "songs.json")
themes = load_themes(THEMES_DIR)
library = build_default_library(json_path=SONGS_JSON)


@app.get("/api/health")
def health():
    return {"ok": True, "themes": len(themes), "songs": len(library.mastered())}


@app.get("/api/themes")
def api_themes():
    return [{"name": t.name, "prefix": t.output_prefix,
             "watermark_fix": t.watermark_fix,
             "backgrounds": t.backgrounds,
             "notes": t.notes} for t in themes.values()]


@app.get("/api/layouts")
def api_layouts():
    return list_layouts()


@app.get("/api/layouts/{layout_id}/params")
def api_layout_params(layout_id: str):
    try:
        return layout_params(layout_id)
    except KeyError as e:
        return Response(str(e), status_code=404)


@app.get("/api/songs")
def api_songs():
    return {"total": len(library.mastered()),
            "by_len": _count_by_len()}


@app.get("/api/songs/list")
def api_songs_list(status: str = None):
    """返回完整歌曲列表，可按 status 过滤（active/draft）。"""
    songs = library.songs
    if status:
        songs = [s for s in songs if s.status == status]
    return {"total": len(songs),
            "active": library.count_active(),
            "draft": library.count_draft(),
            "songs": [{"title": s.title, "status": s.status,
                       "section": s.section, "artists": s.artists}
                      for s in songs]}


@app.get("/api/render")
def api_render(theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    if theme not in themes:
        return Response(f"未知主题：{theme}", status_code=404)
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    base = CANVAS_PRESETS.get(canvas, CANVAS_PRESETS["标准 9:16"])
    spec = base
    if avoid:
        spec = replace(spec, avoid_zones=((940, 1080, 1080, base.height),))
    # 排版参数覆盖（对应插件 ParamSpec 的 key，未传则用预设默认值）
    overrides = {k: v for k, v in
                 {"margin": margin, "font_song": font_song,
                  "row_h": row_h, "sec_gap": sec_gap}.items()
                 if v is not None}
    if overrides:
        spec = replace(spec, **overrides)
    img = render_page(themes[theme], layout_plugin, library, spec, page, FONT)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


def _count_by_len():
    out = {}
    for s in library.mastered():
        n = len(s.title)
        key = str(n) if n <= 6 else "7+"
        out[key] = out.get(key, 0) + 1
    return out
