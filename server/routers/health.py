"""P0-4b: 本地后端健康检查端点。

设计要点：
- 不在 mutate 白名单里（GET），不需要 session token；
- 不读盘（不检查数据完整性，那属于 startup 阶段），只确认 FastAPI 进程在跑；
- 渲染层用它做 localBackend 状态探针 —— 区分 "navigator.onLine=false" 和
  "本机后端未启动" 两种不同情况。
- 返回值包含 mode（development/production）便于诊断，
  不返回 data_dir 路径以免泄露文件系统结构。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/health")
def health(request: Request) -> JSONResponse:
    """轻量 ping 端点。返回 200 + 服务元信息。"""
    config = request.app.state.config
    return JSONResponse(
        {
            "ok": True,
            "mode": config.mode,
            "session_required": bool(config.session_token),
            "request_id": getattr(request.state, "request_id", None),
        }
    )
