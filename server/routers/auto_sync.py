"""M2.4 WebDAV 自动同步 HTTP 端点。

- GET    /api/backup/webdav/auto-sync      读 status + 配置
- POST   /api/backup/webdav/auto-sync      启用 / 关闭 / 调间隔 / 调方向
- POST   /api/backup/webdav/auto-sync/run  立即触发一次（用明文主密码）
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    AutoSyncSettingsRequest,
    AutoSyncRunRequest,
    OkResponse,
)
from server.dependencies import get_app_context


router = APIRouter()


def _payload(payload) -> dict:
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


@router.get("/api/backup/webdav/auto-sync")
def api_autosync_get(req: Request):
    """读当前自动同步配置 + 上次执行状态。"""
    settings = get_app_context(req).settings_service.get()
    return {
        "enabled": bool(settings.get("webdav_auto_sync_enabled")),
        "interval_minutes": int(settings.get(
            "webdav_auto_sync_interval_minutes") or 60),
        "direction": settings.get("webdav_auto_sync_direction") or "push",
        "last_at": settings.get("webdav_auto_sync_last_at"),
        "last_status": settings.get("webdav_auto_sync_last_status"),
        "last_error": settings.get("webdav_auto_sync_last_error"),
        "last_remote_name": settings.get("webdav_auto_sync_last_remote_name"),
        "has_webdav_config": bool(settings.get("webdav_config_encrypted")),
        "has_master_password": bool(settings.get(
            "webdav_auto_sync_master_password_b64")),
    }


@router.post("/api/backup/webdav/auto-sync")
async def api_autosync_set(payload: AutoSyncSettingsRequest, req: Request):
    """启用 / 关闭 / 调间隔 / 调方向 + 可选主密码（启用时必填）。

    enabled=false 时清掉主密码字段（避免主密码残留在 settings.json）。
    """
    context = get_app_context(req)
    body = _payload(payload)
    from server.services.auto_sync import _encode_master
    changes: dict = {}
    if "enabled" in body:
        changes["webdav_auto_sync_enabled"] = bool(body["enabled"])
    if "interval_minutes" in body:
        changes["webdav_auto_sync_interval_minutes"] = int(body["interval_minutes"])
    if "direction" in body:
        changes["webdav_auto_sync_direction"] = str(body["direction"])
    enabled = changes.get("webdav_auto_sync_enabled")
    if enabled is True:
        # 启用时必须提供主密码
        if not body.get("master_password"):
            return api_error_response(
                req, 422,
                ApiError("missing_master_password",
                         "启用自动同步必须提供主密码（用于解锁加密 config）"))
        changes["webdav_auto_sync_master_password_b64"] = _encode_master(
            body["master_password"])
    elif enabled is False:
        # 关闭时清掉主密码
        changes["webdav_auto_sync_master_password_b64"] = None
    try:
        new_settings = context.settings_service.update(changes)
    except Exception as exc:
        return api_error_response(
            req, 422,
            ApiError("settings_update_failed", f"更新设置失败: {exc}"))
    # 启停时通知 scheduler 重启
    scheduler = getattr(context, "auto_sync_scheduler", None)
    if scheduler is not None:
        try:
            if new_settings.get("webdav_auto_sync_enabled"):
                await scheduler.start()
            else:
                await scheduler.stop()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("scheduler 启停失败")
    return {"ok": True, "settings": api_autosync_get(req)}


@router.post("/api/backup/webdav/auto-sync/run")
async def api_autosync_run(payload: AutoSyncRunRequest, req: Request):
    """立即触发一次同步。需要主密码（明文）。"""
    context = get_app_context(req)
    body = _payload(payload)
    master = body.get("master_password") or ""
    if not master:
        return api_error_response(
            req, 422,
            ApiError("missing_master_password", "立即同步必须提供主密码"))
    scheduler = getattr(context, "auto_sync_scheduler", None)
    if scheduler is None:
        return api_error_response(
            req, 503,
            ApiError("scheduler_unavailable", "自动同步调度器未启动"))
    result = await scheduler.trigger(master)
    status = 200 if result.get("ok") else 500
    return {"ok": result.get("ok", False), "result": result}
