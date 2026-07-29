"""导出路由（/api/export*）。"""
import sys
import subprocess
import uuid
from pathlib import Path
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Query, Request

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    ExportBatchRequest,
    ExportBatchResponse,
    ExportJobResponse,
    ExportOpenResponse,
    ExportRequest,
    ExportResponse,
)
from server.dependencies import get_app_context
from core.spec import get_canvas_spec
from core.layouts import get_layout
from server.services.export import ExportJobInput, ExportTarget, run_export_job
from server.services.render_document import build_render_document

router = APIRouter()


@router.post("/api/export", response_model=ExportResponse)
def api_export(req: Request, query: Annotated[ExportRequest, Query()]):
    theme, page = query.theme, query.page
    canvas, avoid, layout = query.canvas, query.avoid, query.layout
    margin, font_song = query.margin, query.font_song
    row_h, sec_gap = query.row_h, query.sec_gap
    context = get_app_context(req)
    themes = context.themes
    songs = context.song_repository.load()
    settings = context.settings_repository.load()
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
        return api_error_response(
            req, 500, ApiError(
                "export_failed", "导出失败",
                recovery="检查输出目录权限与磁盘空间后重试",
            ))
    return {"ok": True, "path": str(out_path), "filename": filename,
            "duration_ms": job["total_ms"]}


@router.post("/api/export/batch", response_model=ExportBatchResponse)
def api_export_batch(req: Request, query: Annotated[ExportBatchRequest, Query()]):
    layout, canvas, avoid = query.layout, query.canvas, query.avoid
    context = get_app_context(req)
    themes = context.themes
    songs = context.song_repository.load()
    settings = context.settings_repository.load()
    font = str(context.paths.fonts_dir / "MaokenAssortedSans.ttf")
    try:
        layout_plugin = get_layout(layout)
    except KeyError as e:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(e)))
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


@router.get("/api/export/jobs/{job_id}", response_model=ExportJobResponse)
def api_export_job(job_id: str, req: Request):
    jobs = get_app_context(req).export_job_manager
    job = jobs.get(job_id)
    if job is None:
        return api_error_response(
            req, 404, ApiError("export_job_not_found", f"未知任务：{job_id}"))
    return job


@router.post("/api/export/open", response_model=ExportOpenResponse)
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
        return api_error_response(
            req, 500, ApiError(
                "open_output_directory_failed",
                "打开输出目录失败",
                recovery="检查输出目录后重试",
            ))
    return {"ok": True, "output_dir": out_dir}
