"""本地渲染后端（开发期）。

FastAPI 暴露渲染/主题/歌曲接口。前端（浏览器或后期 Electron BrowserWindow）连
http://localhost:8000 调用。MVP 后期由 Electron 把本服务打包为 child_process。

运行（项目根目录下）：
    pip install -r requirements.txt
    uvicorn server.main:app --reload --port 8000
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import replace, asdict
from datetime import datetime

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
SETTINGS_PATH = os.path.join(ROOT, "data", "settings.json")
themes = load_themes(THEMES_DIR)
library = build_default_library(json_path=SONGS_JSON)

# ---- 应用设置（settings.json）----
DEFAULT_SETTINGS = {
    "output_dir": os.path.join(ROOT, "output"),
    "default_canvas": "抖音全屏 9:20",
    "default_theme": "海洋柔光",
    "font_path": FONT,
    "backup_count": 20,
    "render_threads": 1,
}

def _load_settings() -> dict:
    if os.path.isfile(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    return DEFAULT_SETTINGS.copy()

def _save_settings(s: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

settings = _load_settings()


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


@app.post("/api/songs/status")
def api_songs_status(payload: dict):
    """切换歌曲状态：{"title": "知足", "status": "active"|"draft"}。

    一键「学会了」（draft→active）/「标回未会」（active→draft）。
    变更即原子写落盘 + 自动备份（data/backups/，滚动保留）。
    渲染端点每次新排文字层，无需额外缓存失效。
    """
    title = (payload.get("title") or "").strip()
    status = (payload.get("status") or "").strip()
    if status not in ("active", "draft"):
        return Response("status 必须是 active 或 draft", status_code=400)
    mark = library.mark_active if status == "active" else library.mark_draft
    if not mark(title):
        return Response(f"未找到歌曲：{title}", status_code=404)
    backup_dir = os.path.join(ROOT, "data", "backups")
    library.save(SONGS_JSON, backup_dir=backup_dir,
                 backup_count=settings.get("backup_count", 20))
    return {"ok": True, "title": title, "status": status,
            "active": library.count_active(), "draft": library.count_draft()}


# ---- 导出 ----
@app.post("/api/export")
def api_export(theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    """导出单页 PNG 到输出目录，返回文件路径。"""
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
    overrides = {k: v for k, v in
                 {"margin": margin, "font_song": font_song,
                  "row_h": row_h, "sec_gap": sec_gap}.items()
                 if v is not None}
    if overrides:
        spec = replace(spec, **overrides)

    t0 = time.perf_counter()
    img = render_page(themes[theme], layout_plugin, library, spec, page, FONT)
    duration = time.perf_counter() - t0

    # 输出命名：{prefix}-{layout_id}-{tag}-{page}.png
    tag = "糖圆体全屏绕排" if avoid and spec.height > 1920 else "糖圆体"
    filename = f"{themes[theme].output_prefix}-{layout}-{tag}-{page}.png"
    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    img.save(out_path, "PNG")

    return {"ok": True, "path": out_path, "filename": filename,
            "duration_ms": round(duration * 1000, 1)}


# ---- 批量导出任务（后台线程 + 进度查询）----
_EXPORT_JOBS: dict = {}


def _run_batch_job(job_id: str, layout_plugin, spec, out_dir: str):
    job = _EXPORT_JOBS[job_id]
    t0 = time.perf_counter()
    try:
        for tname, theme in themes.items():
            for page in range(1, (layout_plugin.pages or 2) + 1):
                job["current"] = f"{tname} p{page}"
                img = render_page(theme, layout_plugin, library, spec, page, FONT)
                tag = "糖圆体全屏绕排" if spec.avoid_zones and spec.height > 1920 else "糖圆体"
                filename = f"{theme.output_prefix}-{layout_plugin.id}-{tag}-{page}.png"
                out_path = os.path.join(out_dir, filename)
                img.save(out_path, "PNG")
                job["files"].append({"theme": tname, "page": page, "path": out_path})
                job["done"] += 1
        job["status"] = "done"
    except Exception as e:  # 任务失败也要让前端能查到
        job["status"] = "error"
        job["error"] = str(e)
    job["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)


@app.post("/api/export/batch")
def api_export_batch(layout: str = "grid-wrap",
                     canvas: str = "抖音全屏 9:20", avoid: bool = True):
    """启动批量导出（当前排版 × 全部主题 × 全部页）。

    立即返回 job_id，后台线程渲染；前端轮询 /api/export/jobs/{job_id}
    获取进度（done/total/current/status）。
    """
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    base = CANVAS_PRESETS.get(canvas, CANVAS_PRESETS["抖音全屏 9:20"])
    spec = base
    if avoid:
        spec = replace(spec, avoid_zones=((940, 1080, 1080, base.height),))

    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    pages = layout_plugin.pages or 2
    job_id = uuid.uuid4().hex[:8]
    _EXPORT_JOBS[job_id] = {
        "status": "running", "done": 0, "total": len(themes) * pages,
        "current": "", "files": [], "output_dir": out_dir,
        "total_ms": None, "error": None,
    }
    threading.Thread(target=_run_batch_job,
                     args=(job_id, layout_plugin, spec, out_dir),
                     daemon=True).start()
    return {"ok": True, "job_id": job_id, "total": len(themes) * pages}


@app.get("/api/export/jobs/{job_id}")
def api_export_job(job_id: str):
    """查询批量导出任务进度。"""
    job = _EXPORT_JOBS.get(job_id)
    if job is None:
        return Response(f"未知任务：{job_id}", status_code=404)
    return job


@app.post("/api/export/open")
def api_export_open():
    """在系统文件管理器中打开输出目录（macOS Finder / Windows 资源管理器）。"""
    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", out_dir])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", out_dir])
        else:
            subprocess.Popen(["xdg-open", out_dir])
    except Exception as e:
        return Response(f"打开目录失败：{e}", status_code=500)
    return {"ok": True, "output_dir": out_dir}


# ---- 设置 ----
@app.get("/api/settings")
def api_settings_get():
    return settings


@app.post("/api/settings")
def api_settings_update(new_settings: dict):
    settings.update(new_settings)
    _save_settings(settings)
    return {"ok": True, "settings": settings}


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
