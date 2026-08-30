"""M2.4 WebDAV 自动同步 HTTP 端点（P0-1 已切到 secret_store）。

- GET    /api/backup/webdav/auto-sync      读 status + 配置 + 密钥环 backend 名
- POST   /api/backup/webdav/auto-sync      启用 / 关闭 / 调间隔 / 调方向 + 写主密码到密钥环
- POST   /api/backup/webdav/auto-sync/run  立即触发一次（用明文主密码）

P0-1（2026-08-30 8/18 评估 6.5）：
- 主密码不再以 base64 形式落到 settings；改用 core.secret_store（系统 Keychain）
- 旧字段 webdav_auto_sync_master_password_b64 在 _normalize 时被静默擦除
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from core import secret_store
from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    AutoSyncSettingsRequest,
    AutoSyncRunRequest,
)
from server.dependencies import get_app_context


router = APIRouter()


def _payload(payload) -> dict:
    return (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else payload)


@router.get("/api/backup/webdav/auto-sync")
def api_autosync_get(req: Request):
    """读当前自动同步配置 + 上次执行状态 + 密钥环 backend 状态。"""
    settings = get_app_context(req).settings_service.get()
    # P0-1：has_master_password 改读密钥环
    has_master = False
    if secret_store.is_available():
        try:
            has_master = bool(secret_store.get_secret("settings-master"))
        except secret_store.SecretStoreUnavailable:
            has_master = False
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
        "has_master_password": has_master,
        # P0-1：让 UI 能展示「存在密钥环，但当前 backend 不可用」这种状态
        "secret_store_available": secret_store.is_available(),
        "secret_store_backend": secret_store.backend_name(),
    }


@router.post("/api/backup/webdav/auto-sync")
async def api_autosync_set(payload: AutoSyncSettingsRequest, req: Request):
    """启用 / 关闭 / 调间隔 / 调方向 + 可选主密码（启用时必填）。

    P0-1：主密码写到系统密钥环（secret_store.set_secret），不写 settings。
    关闭时清掉密钥环项（secret_store.delete_secret）。
    """
    context = get_app_context(req)
    body = _payload(payload)
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
        # P0-1：先检查密钥环可用，否则 503 提示用户
        if not secret_store.is_available():
            return api_error_response(
                req, 503,
                ApiError("secret_store_unavailable",
                         f"系统密钥环不可用: {secret_store.backend_name()}; "
                         f"自动同步已关闭"))
        try:
            secret_store.set_secret("settings-master", body["master_password"])
        except secret_store.SecretStoreUnavailable as exc:
            return api_error_response(
                req, 503,
                ApiError("secret_store_unavailable", str(exc)))
    elif enabled is False:
        # 关闭时清掉密钥环项（如果存在）
        if secret_store.is_available():
            try:
                secret_store.delete_secret("settings-master")
            except secret_store.SecretStoreUnavailable:
                pass  # 不可用时忽略；下个 tick 不会再用
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
