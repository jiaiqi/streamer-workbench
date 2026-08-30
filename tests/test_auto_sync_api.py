"""M2.4 WebDAV 自动同步后端 API + 调度器测试。

覆盖：
- GET /api/backup/webdav/auto-sync 读默认状态
- POST 启用自动同步（需主密码）+ 422 missing_master_password
- POST 关闭自动同步（清掉主密码）
- 校验：interval/direction 非法值 422
- POST /api/backup/webdav/auto-sync/run 422 missing_master_password
- AutoSyncScheduler.run_once(): 5 个分支 — 无 config / 无主密码 / 成功 push / 失败 / 写 status
- settings 字段持久化：enable/disable/interval/direction 双向
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig
from server.services.auto_sync import (
    AutoSyncScheduler,
    MASTER_ACCOUNT,
)
from tests.test_api_contract import _request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


def _run(coro):
    return asyncio.run(coro)


# ── HTTP 端点 ────────────────────────────────────────────

class AutoSyncApiTests(unittest.TestCase):

    def test_get_default_state(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "GET", "/api/backup/webdav/auto-sync")
                    assert status == 200, body
                    assert body["enabled"] is False
                    assert body["interval_minutes"] == 60
                    assert body["direction"] == "push"
                    assert body["last_at"] is None
                    assert body["has_webdav_config"] is False
                    assert body["has_master_password"] is False
        _run(scenario())

    def test_set_enabled_requires_master_password(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    # 没传 master_password → 422
                    status, body, _ = await _request(
                        app, "POST", "/api/backup/webdav/auto-sync",
                        {"enabled": True, "interval_minutes": 30})
                    assert status == 422, body
                    assert body.get("error", {}).get("code") == "missing_master_password"
        _run(scenario())

    def test_set_enabled_with_master_persists(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/backup/webdav/auto-sync",
                        {"enabled": True, "interval_minutes": 15,
                         "direction": "both", "master_password": "secret"})
                    assert status == 200, body
                    s = body["settings"]
                    assert s["enabled"] is True
                    assert s["interval_minutes"] == 15
                    assert s["direction"] == "both"
                    assert s["has_master_password"] is True
        _run(scenario())

    def test_set_disabled_clears_master(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    # 先启用
                    await _request(
                        app, "POST", "/api/backup/webdav/auto-sync",
                        {"enabled": True, "master_password": "x"})
                    # 再关闭
                    status, body, _ = await _request(
                        app, "POST", "/api/backup/webdav/auto-sync",
                        {"enabled": False})
                    assert status == 200, body
                    s = body["settings"]
                    assert s["enabled"] is False
                    assert s["has_master_password"] is False
        _run(scenario())

    def test_set_invalid_interval_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/backup/webdav/auto-sync",
                        {"interval_minutes": 9999})
                    # 9999 > 1440 max → Pydantic Field(le=1440) 422
                    assert status == 422
        _run(scenario())

    def test_run_requires_master_password(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    # 空 body → Pydantic 必填校验 422 (master_password 缺)
                    status, body, _ = await _request(
                        app, "POST", "/api/backup/webdav/auto-sync/run",
                        {})
                    assert status == 422
                    # 缺 master_password 字段 → 应用层校验 422
                    status, body, _ = await _request(
                        app, "POST", "/api/backup/webdav/auto-sync/run",
                        {"other": "x"})
                    assert status == 422
        _run(scenario())

    # ── P0-1：secret_store 不可用 / 旧字段擦除 ──

    def test_get_includes_secret_store_status(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "GET", "/api/backup/webdav/auto-sync")
                    assert status == 200
                    # P0-1 新字段
                    assert "secret_store_available" in body
                    assert "secret_store_backend" in body
                    # 当前环境（macOS CI）一定可用
                    assert body["secret_store_available"] is True
                    self.assertIsInstance(body["secret_store_backend"], str)
        _run(scenario())

    def test_set_enabled_when_secret_store_unavailable_503(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    # mock secret_store 不可用
                    with patch("core.secret_store.is_available", return_value=False), \
                         patch("core.secret_store.backend_name",
                               return_value="Mocked Unavailable"):
                        status, body, _ = await _request(
                            app, "POST", "/api/backup/webdav/auto-sync",
                            {"enabled": True, "master_password": "secret"})
                        assert status == 503
                        assert body.get("error", {}).get("code") == "secret_store_unavailable"
        _run(scenario())

    def test_old_master_password_field_is_silently_dropped(self):
        """P0-1 向前兼容：旧 settings.json 里的 base64 字段被静默擦除。"""
        from server.services.settings import SettingsApplicationService
        from server.repositories.settings import FileSettingsRepository
        from server.ports.repositories import BackupPolicy
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backup_dir = root / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            # 模拟旧 settings.json 含有 base64 字段 + 必要默认
            (root / "settings.json").write_text(
                '{"webdav_auto_sync_master_password_b64": "c2VjcmV0",'
                ' "schemaVersion": 1,'
                ' "output_dir": "/tmp/x",'
                ' "default_canvas": "9:16",'
                ' "default_theme": "ocean",'
                ' "font_path": "/tmp/font.ttf",'
                ' "backup_count": 5,'
                ' "render_threads": 1}', encoding="utf-8")
            settings = SettingsApplicationService(
                settings_repository=FileSettingsRepository(
                    root / "settings.json", BackupPolicy(backup_dir)))
            normalized = settings.get()
            assert "webdav_auto_sync_master_password_b64" not in normalized


# ── AutoSyncScheduler.run_once 分支 ─────────────────────────

class AutoSyncSchedulerTests(unittest.TestCase):
    """覆盖 scheduler.run_once() 的 4 个分支："""

    def _make_app_with_scheduler(self, td: Path):
        from server.app import create_app
        app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(td)))
        return app

    def test_no_webdav_config_skipped(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = self._make_app_with_scheduler(Path(td))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    scheduler: AutoSyncScheduler = ctx.auto_sync_scheduler
                    result = await scheduler.run_once()
                    assert result["ok"] is False
                    assert result["skipped"] == "no_webdav_config"
                    # status 已写入 settings
                    s = ctx.settings_service.get()
                    assert s["webdav_auto_sync_last_status"] == "skipped"
                    assert s["webdav_auto_sync_last_at"] is not None
        _run(scenario())

    def test_no_master_password_skipped(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = self._make_app_with_scheduler(Path(td))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    # 模拟：有加密 config 但密钥环中无 master
                    # P0-1：清掉密钥环中可能残留的 master（其他测试残留）
                    from core import secret_store
                    try:
                        secret_store.delete_secret(MASTER_ACCOUNT)
                    except Exception:
                        pass
                    ctx.settings_service.update({
                        "webdav_config_encrypted": {"cipher_b64": "AAAA"},
                    })
                    scheduler = ctx.auto_sync_scheduler
                    result = await scheduler.run_once()
                    assert result["ok"] is False
                    assert result["skipped"] == "no_master_password"
        _run(scenario())

    def test_run_push_success(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = self._make_app_with_scheduler(Path(td))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    # P0-1：把 master 写到系统密钥环
                    from core import secret_store
                    try:
                        secret_store.delete_secret(MASTER_ACCOUNT)
                    except Exception:
                        pass
                    secret_store.set_secret(MASTER_ACCOUNT, "pw")
                    # mock settings 只有 config（旧 master 字段不再写）
                    ctx.settings_service.update({
                        "webdav_config_encrypted": {"cipher_b64": "AAAA"},
                    })
                    scheduler = ctx.auto_sync_scheduler
                    # mock webdav.auto_run_once 返回成功
                    with patch.object(
                        ctx.webdav_service, "auto_run_once",
                        return_value={
                            "ok": True,
                            "push": {"ok": True, "remote_name": "song-20260809.songworkbench"},
                            "pull": None,
                        },
                    ):
                        result = await scheduler.run_once()
                        assert result["ok"] is True
                        assert result["push"]["remote_name"] == "song-20260809.songworkbench"
                    s = ctx.settings_service.get()
                    assert s["webdav_auto_sync_last_status"] == "success"
                    assert s["webdav_auto_sync_last_remote_name"] == "song-20260809.songworkbench"
                    # 清理
                    secret_store.delete_secret(MASTER_ACCOUNT)
        _run(scenario())

    def test_run_push_failure_writes_error(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = self._make_app_with_scheduler(Path(td))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    from core import secret_store
                    try:
                        secret_store.delete_secret(MASTER_ACCOUNT)
                    except Exception:
                        pass
                    secret_store.set_secret(MASTER_ACCOUNT, "pw")
                    ctx.settings_service.update({
                        "webdav_config_encrypted": {"cipher_b64": "AAAA"},
                    })
                    scheduler = ctx.auto_sync_scheduler
                    with patch.object(
                        ctx.webdav_service, "auto_run_once",
                        return_value={"ok": False, "error": "auth_failed: 401"},
                    ):
                        result = await scheduler.run_once()
                        assert result["ok"] is False
                        assert "auth_failed" in result["error"]
                    s = ctx.settings_service.get()
                    assert s["webdav_auto_sync_last_status"] == "failed"
                    assert "auth_failed" in s["webdav_auto_sync_last_error"]
                    secret_store.delete_secret(MASTER_ACCOUNT)
        _run(scenario())

    def test_master_password_roundtrip(self):
        # P0-1：直接验证密钥环的 roundtrip（旧 base64 helper 已删除）
        from core import secret_store
        try:
            secret_store.delete_secret(MASTER_ACCOUNT)
        except Exception:
            pass
        secret_store.set_secret(MASTER_ACCOUNT, "hello世界")
        assert secret_store.get_secret(MASTER_ACCOUNT) == "hello世界"
        secret_store.delete_secret(MASTER_ACCOUNT)
        assert secret_store.get_secret(MASTER_ACCOUNT) is None


if __name__ == "__main__":
    unittest.main()
