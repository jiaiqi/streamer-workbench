"""导出路由（/api/export*）。"""
import sys
import subprocess
import uuid
from pathlib import Path
from dataclasses import replace

from fastapi import APIRouter, Request, Response

from server.dependencies import get_app_context
from core.spec import get_canvas_spec
from core.layouts import get_layout
from server.services.export import ExportJobInput, ExportTarget, run_export_job
from server.services.render_document import build_render_document

router = APIRouter()


@router.post("/api/export")
def api_export(req: Request,
               theme: str, page: int = 1,
               canvas: str = "标准 9:16", avoid: bool = False,
               layout: str = "grid-wrap",
               margin: int = None, font_song: int = None,
               row_h: int = None, sec_gap: int = None):
    context = get_app_context(req)
    themes = context.themes
    songs = context.song_repository.load()
    settings = context.settings_repository.load()
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

    tag = "糖圆体全屏绕排" if avoid and spec.height > 1920 else "糖圆体"
    filename = f"{themes[theme].output_prefix}-{layout}-{tag}-{page}.png"
    out_path = Path(settings.value["output_dir"]) / filename
    document = build_render_document(
        song_snapshot=songs, theme=themes[theme], layout_id=layout_plugin.id,
        canvas=spec, page=page, font_path=font,
        settings_revision=settings.revision, parameters=overrides)
    job_id = uuid.uuid4().hex[:8]
    job = {"status": "running", "done": 0, "total": 1, "current": "",
           "files": [], "output_dir": str(out_path.parent), "total_ms": None, "error": None}
    run_export_job(ExportJobInput(job_id, (document,),
                                  (ExportTarget(out_path, theme, page),),
                                  context.event_store, job))
    if job["status"] == "error":
        return Response(f"导出失败：{job['error']}", status_code=500)
    return {"ok": True, "path": str(out_path), "filename": filename,
            "duration_ms": job["total_ms"]}


@router.post("/api/export/batch")
def api_export_batch(req: Request,
                     layout: str = "grid-wrap",
                     canvas: str = "抖音全屏 9:20", avoid: bool = True):
    context = get_app_context(req)
    themes = context.themes
    songs = context.song_repository.load()
    settings = context.settings_repository.load()
    font = str(context.paths.fonts_dir / "MaokenAssortedSans.ttf")
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return Response(str(e), status_code=404)
    spec = get_canvas_spec(canvas, avoid=avoid, default="抖音全屏 9:20")

    out_dir = Path(settings.value["output_dir"])
    pages = layout_plugin.pages or 2
    job_id = uuid.uuid4().hex[:8]
    jobs = context.export_job_manager
    jobs[job_id] = {
        "status": "running", "done": 0, "total": len(themes) * pages,
        "current": "", "files": [], "output_dir": str(out_dir),
        "total_ms": None, "error": None,
    }
    documents = []
    targets = []
    tag = "糖圆体全屏绕排" if spec.avoid_zones and spec.height > 1920 else "糖圆体"
    for theme_name, theme_value in themes.items():
        for page in range(1, pages + 1):
            documents.append(build_render_document(
                song_snapshot=songs, theme=theme_value, layout_id=layout_plugin.id,
                canvas=spec, page=page, font_path=font,
                settings_revision=settings.revision))
            filename = f"{theme_value.output_prefix}-{layout_plugin.id}-{tag}-{page}.png"
            targets.append(ExportTarget(out_dir / filename, theme_name, page))
    job_input = ExportJobInput(job_id, tuple(documents), tuple(targets),
                               context.event_store, jobs[job_id])
    jobs.start(job_input)
    return {"ok": True, "job_id": job_id, "total": len(themes) * pages}


@router.get("/api/export/jobs/{job_id}")
def api_export_job(job_id: str, req: Request):
    jobs = get_app_context(req).export_job_manager
    job = jobs.get(job_id)
    if job is None:
        return Response(f"未知任务：{job_id}", status_code=404)
    return job


@router.post("/api/export/open")
def api_export_open(req: Request):
    settings = get_app_context(req).settings_repository.load().value
    out_dir = settings["output_dir"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
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
