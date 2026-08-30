"""M2.4 WebDAV 自动同步调度器。

设计：
- 后台 asyncio 任务，按 settings 中的 webdav_auto_sync_interval_minutes 间隔轮询
- 启动时根据 webdav_auto_sync_enabled 决定是否启动循环
- settings 改变时（enabled/interval/direction）通过 refresh_from_settings() 重新读
- run_now() 立即触发一次同步（不打断主循环）
- 失败不中断下个 tick；每次结果都写到 settings.last_at/last_status/last_error/last_remote_name

P0-1（2026-08-30 8/18 评估 6.5）：
- 主密码不再 base64 落到 settings；改走 core.secret_store（系统 Keychain）
- 跨平台：macOS Keychain / Windows Credential Manager / Linux Secret Service
- 不可用时：自动同步启动被跳过，run_now 报 503 secret_store_unavailable
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from core import secret_store
from server.services.webdav_sync import (
    WebDavConfigInvalid,
    WebDavSyncService,
)


logger = logging.getLogger(__name__)

# P0-1：主密码在系统密钥环中的 account 标识
# 一个项目只用一个主密码（settings 面板的那个），所以 account 固定
MASTER_ACCOUNT = "settings-master"


def _load_master_password() -> str | None:
    """从系统密钥环读主密码。不可用或未存都返回 None。"""
    try:
        pw = secret_store.get_secret(MASTER_ACCOUNT)
    except secret_store.SecretStoreUnavailable as exc:
        logger.warning("AutoSyncScheduler: 系统密钥环不可用 - %s", exc)
        return None
    return pw


class AutoSyncScheduler:
    """Auto-sync 后台循环控制器。

    用法：
        scheduler = AutoSyncScheduler(webdav_service, settings_service)
        await scheduler.start()        # lifespan startup
        ...
        await scheduler.stop()         # lifespan shutdown
    """

    def __init__(self, *, webdav_service: WebDavSyncService, settings_service):
        self._webdav = webdav_service
        self._settings = settings_service
        self._task: asyncio.Task | None = None
        self._running_lock = asyncio.Lock()  # 防止 run_now 和 tick 同时跑

    # ── 生命周期 ──

    async def start(self) -> None:
        settings = self._settings.get()
        if not settings.get("webdav_auto_sync_enabled"):
            logger.info("AutoSyncScheduler: 启动时自动同步 disabled，跳过")
            return
        if not self._has_webdav_config():
            logger.warning("AutoSyncScheduler: enabled 但无 WebDAV 配置，跳过")
            return
        # P0-1：系统密钥环不可用 → 自动同步启动被阻止（评估 6.5）
        if not secret_store.is_available():
            logger.warning(
                "AutoSyncScheduler: 系统密钥环不可用 (%s); 自动同步已拒绝启动",
                secret_store.backend_name())
            self._write_status(
                {"ok": False, "skipped": "secret_store_unavailable"},
                error=f"系统密钥环不可用: {secret_store.backend_name()}")
            return
        # 主密码缺失（用户还没在 WebDavPanel 输入过）也跳过，但不算不可用
        if _load_master_password() is None:
            logger.warning("AutoSyncScheduler: enabled 但密钥环中无主密码，跳过")
            return
        self._task = asyncio.create_task(self._loop(), name="autosync-loop")
        logger.info("AutoSyncScheduler: 启动（间隔 %s 分钟）",
                    settings.get("webdav_auto_sync_interval_minutes"))

    async def stop(self) -> None:
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("AutoSyncScheduler: 已停止")

    def _has_webdav_config(self) -> bool:
        """检查 settings 是否有加密的 webdav config。"""
        try:
            settings = self._settings.get()
        except Exception:
            return False
        return bool(settings.get("webdav_config_encrypted"))

    # ── 主循环 ──

    async def _loop(self) -> None:
        while True:
            try:
                settings = self._settings.get()
                if not settings.get("webdav_auto_sync_enabled"):
                    logger.info("AutoSyncScheduler loop: disabled 退出")
                    return
                interval = max(1, int(settings.get(
                    "webdav_auto_sync_interval_minutes") or 60))
                await self.run_once()
                await asyncio.sleep(interval * 60)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("AutoSyncScheduler tick 失败；下个周期继续")
                # 失败不退出；下个 tick 重试
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise

    # ── 手动触发 ──

    async def run_once(self) -> dict[str, Any]:
        """执行一次同步（带 lock 防并发）；返回结果。"""
        async with self._running_lock:
            return await self._run_once_locked()

    async def _run_once_locked(self) -> dict[str, Any]:
        if not self._has_webdav_config():
            result = {"ok": False, "skipped": "no_webdav_config"}
            self._write_status(result, error="尚未配置 WebDAV")
            return result
        # P0-1：从系统密钥环读主密码；不可用 → 报告并停止（评估 6.5）
        if not secret_store.is_available():
            result = {
                "ok": False,
                "skipped": "secret_store_unavailable",
                "hint": f"系统密钥环不可用: {secret_store.backend_name()}; 自动同步已关闭",
            }
            self._write_status(result,
                               error=f"系统密钥环不可用: {secret_store.backend_name()}")
            return result
        master_pw = _load_master_password()
        if not master_pw:
            result = {
                "ok": False,
                "skipped": "no_master_password",
                "hint": "请在 WebDAV 面板「启用自动同步」时设置主密码",
            }
            self._write_status(result, error="缺少自动同步主密码")
            return result
        try:
            result = self._webdav.auto_run_once(master_password=master_pw)
        except WebDavConfigInvalid as exc:
            result = {"ok": False, "error": f"config_invalid: {exc}"}
            self._write_status(result, error=str(exc))
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("auto_run_once 失败")
            result = {"ok": False, "error": f"unknown: {exc}"}
            self._write_status(result, error=str(exc))
            return result
        # 成功
        push_info = result.get("push") or {}
        pull_info = result.get("pull") or {}
        remote_name = (push_info.get("remote_name")
                       or pull_info.get("remote_name"))
        self._write_status(result, remote_name=remote_name)
        return result

    def _write_status(self, result: dict[str, Any], *,
                      remote_name: str | None = None,
                      error: str | None = None) -> None:
        """把 run 结果写到 settings（last_at/last_status/last_error/last_remote_name）。"""
        try:
            now = datetime.now().isoformat(timespec="seconds")
            ok = bool(result.get("ok"))
            skipped = result.get("skipped")
            status = ("success" if ok
                      else ("skipped" if skipped else "failed"))
            changes: dict[str, Any] = {
                "webdav_auto_sync_last_at": now,
                "webdav_auto_sync_last_status": status,
            }
            if error is not None:
                changes["webdav_auto_sync_last_error"] = error[:500]
            elif not ok:
                err = result.get("error") or "unknown"
                changes["webdav_auto_sync_last_error"] = err[:500]
            else:
                changes["webdav_auto_sync_last_error"] = None
            if remote_name:
                changes["webdav_auto_sync_last_remote_name"] = remote_name
            elif not ok:
                changes["webdav_auto_sync_last_remote_name"] = None
            self._settings.update(changes)
        except Exception:  # noqa: BLE001
            logger.exception("AutoSyncScheduler 写 status 失败")

    # ── 立即触发（API 调用） ──

    async def trigger(self, master_password: str) -> dict[str, Any]:
        """API 端用的「立即同步」接口：用户主动解锁后调用。"""
        async with self._running_lock:
            try:
                result = self._webdav.auto_run_once(master_password=master_password)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc)}
            self._write_status(
                result,
                remote_name=(result.get("push") or {}).get("remote_name")
                            or (result.get("pull") or {}).get("remote_name"),
            )
            return result

