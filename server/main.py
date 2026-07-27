"""本地渲染后端 — 应用装配。

运行：
    uvicorn server.main:app --reload --port 8000
"""
import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.deps import init_deps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("streamer-workbench")

app = FastAPI(title="主播工作台 · 渲染后端")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 初始化服务依赖 ──
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
init_deps(app, ROOT)

# ── 静态挂载 ──
THEMES_DIR = os.path.join(ROOT, "themes")
TABS_DIR = os.path.join(ROOT, "data", "tabs")
app.mount("/bg", StaticFiles(directory=THEMES_DIR), name="theme_bg")
app.mount("/tabs", StaticFiles(directory=TABS_DIR), name="song_tabs")

# ── 注册路由 ──
from server.routers import songs, render, export, events, settings, presets
app.include_router(songs.router)
app.include_router(render.router)
app.include_router(export.router)
app.include_router(events.router)
app.include_router(settings.router)
app.include_router(presets.router)


@app.get("/api/health")
def health():
    from server.deps import get_themes, get_library
    themes = get_themes(app.state)
    library = get_library(app.state)
    return {"ok": True, "themes": len(themes), "songs": len(library.mastered())}


logger.info("后端启动完成，端口 8000")
