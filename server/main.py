"""本地渲染后端（开发期）。

FastAPI 暴露渲染/主题/歌曲接口。前端（浏览器或后期 Tauri webview）连
http://localhost:8000 调用。MVP 后期由 Tauri 把本服务打包成 sidecar。

运行（项目根目录下）：
    pip install -r requirements.txt
    uvicorn server.main:app --reload --port 8000
"""

import io
import os

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from core.spec import CanvasSpec, CANVAS_PRESETS
from core.themes.loader import load_themes
from core.layouts import get_layout
from core.data.songs import build_default_library
from core.engine import render_page

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT, "themes")
FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")

app = FastAPI(title="歌单海报生成器 · 渲染后端")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 开发期放开；生产期收窄到 Tauri 域名
    allow_methods=["*"],
    allow_headers=["*"],
)

themes = load_themes(THEMES_DIR)
library = build_default_library()


@app.get("/api/health")
def health():
    return {"ok": True, "themes": len(themes), "songs": len(library.mastered())}


@app.get("/api/themes")
def api_themes():
    return [{"name": t.name, "prefix": t.output_prefix,
             "watermark_fix": t.watermark_fix} for t in themes.values()]


@app.get("/api/layouts")
def api_layouts():
    from core.layouts import list_layouts
    return list_layouts()


@app.get("/api/songs")
def api_songs():
    return {"total": len(library.mastered()),
            "by_len": _count_by_len()}


@app.get("/api/render")
def api_render(theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False):
    if theme not in themes:
        return Response(f"未知主题：{theme}", status_code=404)
    base = CANVAS_PRESETS.get(canvas, CANVAS_PRESETS["标准 9:16"])
    spec = base
    if avoid:
        spec = CanvasSpec(width=base.width, height=base.height,
                          avoid_zones=((940, 1080, 1080, base.height),))
    layout = get_layout("grid-wrap")
    img = render_page(themes[theme], layout, library, spec, page, FONT)
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
