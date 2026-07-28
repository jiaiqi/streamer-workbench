"""导出路由（/api/export*）。"""
import os
import sys
import subprocess
import threading
import time
import uuid
from dataclasses import replace

from fastapi import APIRouter, Request, Response

from server.deps import get_themes, get_library, get_settings, get_export_jobs
from core.spec import get_canvas_spec
from core.layouts import get_layout
from core.engine import render_page
from core.data.events import append_event

router = APIRouter()


def _run_batch_job(job_id: str, themes, layout_plugin, spec, out_dir, library, font):
    from server.deps import EVENTS_JSONL
    jobs = _get_global_jobs()
    job = jobs[job_id]
    t0 = time.perf_counter()
    try:
        for tname, theme in themes.items():
            for page in range(1, (layout_plugin.pages or 2) + 1):
                job["current"] = f"{tname} p{page}"
                img = render_page(theme, layout_plugin, library, spec, page, font)
                tag = "糖圆体全屏绕排" if spec.avoid_zones and spec.height > 1920 else "糖圆体"
                filename = f"{theme.output_prefix}-{layout_plugin.id}-{tag}-{page}.png"
                out_path = os.path.join(out_dir, filename)
                img.save(out_path, "PNG")
                job["files"].append({"theme": tname, "page": page, "path": out_path})
                job["done"] += 1
        job["status"] = "done"
        job["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        append_event(EVENTS_JSONL, "poster_exported", meta={
            "batch": True, "files": len(job["files"]), "total_ms": job["total_ms"]})
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
    if job["total_ms"] is None:
        job["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)


_EXPORT_JOBS_REF = None


def _get_global_jobs():
    global _EXPORT_JOBS_REF
    return _EXPORT_JOBS_REF


@router.post("/api/export")
def api_export(req: Request,
               theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    themes = get_themes(req.app.state)
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
    from server.deps import FONT, EVENTS_JSONL
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

    t0 = time.perf_counter()
    img = render_page(themes[theme], layout_plugin, library, spec, page, FONT)
    duration = time.perf_counter() - t0

    tag = "糖圆体全屏绕排" if avoid and spec.height > 1920 else "糖圆体"
    filename = f"{themes[theme].output_prefix}-{layout}-{tag}-{page}.png"
    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    img.save(out_path, "PNG")

    append_event(EVENTS_JSONL, "poster_exported", meta={
        "theme": theme, "layout": layout, "canvas": canvas, "page": page,
        "duration_ms": round(duration * 1000, 1)})
    return {"ok": True, "path": out_path, "filename": filename,
            "duration_ms": round(duration * 1000, 1)}


@router.post("/api/export/batch")
def api_export_batch(req: Request,
                     layout: str = "grid-wrap",
                     canvas: str = "抖音全屏 9:20", avoid: bool = True):
    themes = get_themes(req.app.state)
    library = get_library(req.app.state)
    settings = get_settings(req.app.state)
    from server.deps import FONT, EVENTS_JSONL
    global _EXPORT_JOBS_REF
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    spec = get_canvas_spec(canvas, avoid=avoid, default="抖音全屏 9:20")

    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    pages = layout_plugin.pages or 2
    job_id = uuid.uuid4().hex[:8]
    jobs = get_export_jobs(req.app.state)
    _EXPORT_JOBS_REF = jobs
    jobs[job_id] = {
        "status": "running", "done": 0, "total": len(themes) * pages,
        "current": "", "files": [], "output_dir": out_dir,
        "total_ms": None, "error": None,
    }
    threading.Thread(target=_run_batch_job,
                     args=(job_id, themes, layout_plugin, spec, out_dir, library, FONT),
                     daemon=True).start()
    return {"ok": True, "job_id": job_id, "total": len(themes) * pages}


@router.get("/api/export/jobs/{job_id}")
def api_export_job(job_id: str, req: Request):
    jobs = get_export_jobs(req.app.state)
    job = jobs.get(job_id)
    if job is None:
        return Response(f"未知任务：{job_id}", status_code=404)
    return job


@router.post("/api/export/open")
def api_export_open(req: Request):
    settings = get_settings(req.app.state)
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
