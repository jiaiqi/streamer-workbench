"""FastAPI 错误契约、request-id 与异常处理装配。"""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.api.errors import ApiError, map_repository_error
from server.ports.repositories import RepositoryError

logger = logging.getLogger("streamer-workbench")
REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_id(request: Request) -> str:
    state = getattr(request, "state", None)
    return getattr(state, "request_id", None) or f"req_{uuid.uuid4().hex}"


def api_error_response(request: Request, status_code: int, error: ApiError) -> JSONResponse:
    request_id = _request_id(request)
    response = JSONResponse(
        status_code=status_code,
        content=ApiError(
            code=error.code,
            message=error.message,
            details=error.details,
            recovery=error.recovery,
            request_id=request_id,
        ).envelope(),
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def install_api_contract(app: FastAPI) -> None:
    """为 app 安装统一 request-id 与异常响应；可被应用工厂重复使用。"""

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = (
            incoming if _SAFE_REQUEST_ID.fullmatch(incoming)
            else f"req_{uuid.uuid4().hex}"
        )
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        details = {
            "issues": [
                {
                    "location": [str(part) for part in issue.get("loc", ())],
                    "type": issue.get("type", "validation_error"),
                    "message": issue.get("msg", "输入无效"),
                }
                for issue in error.errors()
            ]
        }
        return api_error_response(
            request,
            422,
            ApiError(
                "validation_error",
                "请求参数校验失败",
                details=details,
                recovery="检查标记字段后重新提交",
            ),
        )

    @app.exception_handler(RepositoryError)
    async def repository_error(request: Request, error: RepositoryError):
        status_code, api_error = map_repository_error(error)
        return api_error_response(request, status_code, api_error)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException):
        if error.status_code == 404:
            api_error = ApiError("not_found", "请求的资源不存在", recovery="检查地址后重试")
        else:
            message = error.detail if isinstance(error.detail, str) else "请求失败"
            api_error = ApiError("http_error", message)
        return api_error_response(request, error.status_code, api_error)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, error: Exception):
        request_id = _request_id(request)
        logger.exception("未处理的 API 异常 request_id=%s", request_id, exc_info=error)
        return api_error_response(
            request,
            500,
            ApiError(
                "internal_error",
                "内部错误",
                recovery="重试；若持续失败请查看日志",
            ),
        )
