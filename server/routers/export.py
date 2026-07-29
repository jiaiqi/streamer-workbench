"""导出路由（/api/export*）。"""
import sys
import subprocess
from pathlib import Path
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
from server.services.export import (
    ExportBatchSpec,
    ExportExecutionFailed,
    ExportLayoutNotFound,
    ExportSpec,
    ExportThemeNotFound,
)

router = APIRouter()


@router.post("/api/export", response_model=ExportResponse)
def api_export(req: Request, query: Annotated[ExportRequest, Query()]):
    context = get_app_context(req)
    parameters = {
        "margin": query.margin, "font_song": query.font_song,
        "row_h": query.row_h, "sec_gap": query.sec_gap,
    }
    try:
        result = context.export_service.export_one(ExportSpec(
            theme=query.theme, page=query.page, canvas=query.canvas,
            avoid=query.avoid, layout=query.layout, parameters=parameters))
    except ExportThemeNotFound as error:
        return api_error_response(
            req, 404, ApiError("theme_not_found", str(error)))
    except ExportLayoutNotFound as error:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(error)))
    except ExportExecutionFailed:
        return api_error_response(
            req, 500, ApiError(
                "export_failed", "导出失败",
                recovery="检查输出目录权限与磁盘空间后重试",
            ))
    return {"ok": True, "path": str(result.path),
            "filename": result.filename, "duration_ms": result.duration_ms}


@router.post("/api/export/batch", response_model=ExportBatchResponse)
def api_export_batch(req: Request, query: Annotated[ExportBatchRequest, Query()]):
    context = get_app_context(req)
    try:
        result = context.export_service.enqueue_batch(ExportBatchSpec(
            layout=query.layout, canvas=query.canvas, avoid=query.avoid))
    except ExportLayoutNotFound as error:
        return api_error_response(
            req, 404, ApiError("layout_not_found", str(error)))
    return {"ok": True, "job_id": result.job_id, "total": result.total}


@router.get("/api/export/jobs/{job_id}", response_model=ExportJobResponse)
def api_export_job(job_id: str, req: Request):
    job = get_app_context(req).export_service.job(job_id)
    if job is None:
        return api_error_response(
            req, 404, ApiError("export_job_not_found", f"未知任务：{job_id}"))
    return job


@router.post("/api/export/open", response_model=ExportOpenResponse)
def api_export_open(req: Request):
    out_dir = str(get_app_context(req).export_service.output_directory())
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
