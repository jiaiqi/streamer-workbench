"""M2.2 WebDAV 同步路由（/api/backup/webdav/*）。

错误码约定：
- 400 invalid_webdav_config    配置缺字段 / URL 不合法 / 主密码空
- 401 webdav_auth_failed        远端鉴权失败（账号/密码错）
- 404 webdav_remote_not_found   远端文件/目录不存在
- 502 webdav_remote_unavailable 远端不可达（DNS/SSL/超时/5xx）
- 500 webdav_local_error        本地生成/导入失败
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    WebDavClearRequest,
    WebDavConfigResponse,
    WebDavConfigSaveRequest,
    WebDavConfigSaveResponse,
    WebDavMasterRequest,
    WebDavPullResponse,
    WebDavPushResponse,
    WebDavRemoteListResponse,
    WebDavTestRequest,
    WebDavTestResponse,
)
from server.dependencies import get_app_context
from server.services.webdav_sync import (
    WebDavAuthFailed,
    WebDavConfigInvalid,
    WebDavLocalError,
    WebDavRemoteNotFound,
    WebDavRemoteUnavailable,
)


router = APIRouter()


def _error_response(req: Request, error: Exception):
    """把 service 错误稳定映射成 API error。"""
    if isinstance(error, WebDavConfigInvalid):
        return api_error_response(
            req, 400,
            ApiError("invalid_webdav_config", str(error),
                     recovery="检查 URL / 远端路径 / 主密码后重试"),
        )
    if isinstance(error, WebDavAuthFailed):
        return api_error_response(
            req, 401,
            ApiError("webdav_auth_failed", str(error),
                     recovery="检查 WebDAV 账号密码后重试"),
        )
    if isinstance(error, WebDavRemoteNotFound):
        return api_error_response(
            req, 404,
            ApiError("webdav_remote_not_found", str(error),
                     recovery="确认远端目录存在后重试"),
        )
    if isinstance(error, WebDavRemoteUnavailable):
        return api_error_response(
            req, 502,
            ApiError("webdav_remote_unavailable", str(error),
                     recovery="检查网络 / 远端服务状态后重试"),
        )
    if isinstance(error, WebDavLocalError):
        return api_error_response(
            req, 500,
            ApiError("webdav_local_error", str(error),
                     recovery="查看本地日志；考虑从快照恢复"),
        )
    # 兜底
    return api_error_response(
        req, 500,
        ApiError("internal_error", str(error), recovery="重试；若持续失败请查看日志"),
    )


@router.get("/api/backup/webdav/config", response_model=WebDavConfigResponse)
def webdav_config_get(req: Request, master_password: str | None = None):
    """脱敏读配置。

    master_password 为空：返回 {configured: bool, needs_unlock: True}。
    master_password 提供：尝试解密，错则 400。
    """
    context = get_app_context(req)
    try:
        return context.webdav_service.get_config_public(password=master_password or None)
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)


@router.put("/api/backup/webdav/config", response_model=WebDavConfigSaveResponse)
def webdav_config_save(req: Request, body: WebDavConfigSaveRequest):
    """保存 / 更新 WebDAV 配置（加密存）。"""
    context = get_app_context(req)
    try:
        return context.webdav_service.save_config(
            url=body.url,
            username=body.username,
            password=body.password,
            remote_dir=body.remote_dir,
            master_password=body.master_password,
        )
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)


@router.post("/api/backup/webdav/config/clear", response_model=WebDavConfigSaveResponse)
def webdav_config_clear(req: Request, body: WebDavClearRequest):
    """清除已存的 WebDAV 配置。"""
    context = get_app_context(req)
    try:
        return context.webdav_service.clear_config(master_password=body.master_password)
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)


@router.post("/api/backup/webdav/test", response_model=WebDavTestResponse)
def webdav_test(req: Request, body: WebDavTestRequest):
    """临时凭证测试连接（不写盘）。"""
    context = get_app_context(req)
    try:
        return context.webdav_service.test_connection(
            url=body.url,
            username=body.username,
            password=body.password,
        )
    except Exception as error:
        return api_error_response(
            req, 400,
            ApiError("invalid_webdav_config", str(error),
                     recovery="检查 URL 后重试"),
        )


@router.post("/api/backup/webdav/test-saved", response_model=WebDavTestResponse)
def webdav_test_saved(req: Request, body: WebDavMasterRequest):
    """用已存配置测试连接 + 列远端 backup 目录。"""
    context = get_app_context(req)
    try:
        return context.webdav_service.test_remote_connection(
            master_password=body.master_password,
        )
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)


@router.get("/api/backup/webdav/list", response_model=WebDavRemoteListResponse)
def webdav_list(req: Request, master_password: str):
    """列出远端 backup 目录下的 .songworkbench 文件。"""
    context = get_app_context(req)
    try:
        files = context.webdav_service.list_remote(master_password=master_password)
        return {"files": files}
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)


@router.post("/api/backup/webdav/push", response_model=WebDavPushResponse)
def webdav_push(req: Request, body: WebDavMasterRequest):
    """本地 → 远端：上传新备份。"""
    context = get_app_context(req)
    try:
        return context.webdav_service.push(master_password=body.master_password)
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)


@router.post("/api/backup/webdav/pull", response_model=WebDavPullResponse)
def webdav_pull(req: Request, body: WebDavMasterRequest):
    """远端 → 本地：下载并导入指定远端备份。"""
    if not body.remote_name:
        return api_error_response(
            req, 400,
            ApiError("invalid_webdav_config", "remote_name 必填",
                     recovery="先调用 /list 拿到合法文件名再拉取"),
        )
    context = get_app_context(req)
    try:
        return context.webdav_service.pull(
            master_password=body.master_password,
            remote_name=body.remote_name,
        )
    except (WebDavConfigInvalid, WebDavAuthFailed,
            WebDavRemoteNotFound, WebDavRemoteUnavailable,
            WebDavLocalError) as error:
        return _error_response(req, error)
