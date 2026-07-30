"""R0.9 用户数据目录契约：验证、切换、迁移与回滚的独立回归。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import AppConfig, build_app_paths, resolve_data_root_source
from server.services.data_dir import (
    DataDirectoryService,
    DataDirConflict,
    DataDirUnavailable,
    DataDirValidationFailed,
    STANDARD_SUBDIRS,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _make_service(root: Path, *, mode: str = "test",
                  with_data_root: bool = True):
    """构造服务；启动配置始终指向临时目录，绝不触碰真实用户配置。"""
    startup = root / "startup" / "startup.json"
    config = AppConfig(
        PROJECT_ROOT, mode=mode,
        data_root=(root / "current") if with_data_root else None,
        startup_config_path=startup,
    )
    paths = build_app_paths(config, environ={})
    return DataDirectoryService(config=config, paths=paths, environ={}), paths


def _seed_current_data(paths) -> None:
    paths.data_root.mkdir(parents=True, exist_ok=True)
    (paths.data_root / "songs.json").write_text("{}", encoding="utf-8")
    (paths.data_root / "events.jsonl").write_text("", encoding="utf-8")
    (paths.data_root / "settings.json").write_text("{}", encoding="utf-8")
    (paths.data_root / "tabs").mkdir()
    (paths.data_root / "tabs" / "谱.png").write_bytes(b"png")
    (paths.data_root / "presets").mkdir()
    (paths.data_root / "presets" / "p.json").write_text("{}", encoding="utf-8")
    (paths.data_root / "output").mkdir()
    (paths.data_root / "output" / "poster.png").write_bytes(b"out")
    (paths.data_root / "backups").mkdir()
    (paths.data_root / "backups" / "old.json").write_text("{}", encoding="utf-8")


# ---------- 状态查询 ----------


def test_status_reports_source_labels_and_startup_path():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        status = service.status()
        assert status["current"] == str(paths.data_root)
        assert status["source"] == "explicit"
        assert status["source_label"] == "启动参数"
        assert status["startup_config"] == str(paths.startup_config_path)
        assert status["pinned"] is True


def test_status_source_follows_resolution_priority():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        startup = root / "startup" / "startup.json"
        startup.parent.mkdir(parents=True)
        startup.write_text(json.dumps({"data_root": str(root / "from-startup")}),
                           encoding="utf-8")
        config = AppConfig(PROJECT_ROOT, startup_config_path=startup)
        paths = build_app_paths(config, environ={})
        service = DataDirectoryService(config=config, paths=paths, environ={})
        status = service.status()
        assert status["source"] == "startup"
        assert status["current"] == str((root / "from-startup").resolve())

        dev_config = AppConfig(PROJECT_ROOT,
                               startup_config_path=root / "none" / "startup.json")
        dev_paths = build_app_paths(dev_config, environ={})
        dev_service = DataDirectoryService(config=dev_config, paths=dev_paths,
                                           environ={})
        assert dev_service.status()["source"] == "development"


# ---------- 只读验证 ----------


def test_inspect_rejects_empty_relative_current_and_containment():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        assert service.inspect("") .valid is False
        relative = service.inspect("relative/dir")
        assert relative.valid is False and "绝对路径" in relative.message
        current = service.inspect(str(paths.data_root))
        assert current.valid is False and current.is_current is True
        inside = service.inspect(str(paths.data_root / "child"))
        assert inside.valid is False and "内部" in inside.message
        parent = service.inspect(str(paths.data_root.parent))
        assert parent.valid is False and "父目录" in parent.message


def test_inspect_detects_existing_data_and_writability():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, _paths = _make_service(root)
        target = root / "occupied"
        (target / "tabs").mkdir(parents=True)
        (target / "songs.json").write_text("{}", encoding="utf-8")
        (target / "tabs" / "a.png").write_bytes(b"x")
        inspection = service.inspect(str(target))
        assert inspection.valid is True
        assert inspection.has_existing_data is True
        assert "songs.json" in inspection.existing_items
        assert "tabs/" in inspection.existing_items
        assert inspection.will_initialize is False

        empty = service.inspect(str(root / "fresh"))
        assert empty.valid is True
        assert empty.exists is False
        assert empty.has_existing_data is False
        assert empty.will_initialize is True

        not_dir = root / "a-file"
        not_dir.write_text("x", encoding="utf-8")
        assert service.inspect(str(not_dir)).valid is False


def test_inspect_never_writes():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, _paths = _make_service(root)
        target = root / "no-write"
        service.inspect(str(target))
        assert not target.exists()


# ---------- 切换 ----------


def test_switch_initializes_structure_and_publishes_startup_config():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        target = root / "new home"
        result = service.switch(str(target))
        assert result["ok"] is True
        assert result["requires_restart"] is True
        assert result["migrated"] == []
        assert result["used_existing"] is False
        for name in STANDARD_SUBDIRS:
            assert (target / name).is_dir(), name
        payload = json.loads(paths.startup_config_path.read_text(encoding="utf-8"))
        assert payload["schemaVersion"] == 1
        assert payload["data_root"] == str(target.resolve())
        # 重启后（新进程只读启动配置）解析到新目录，来源为 startup
        fresh = AppConfig(PROJECT_ROOT,
                          startup_config_path=paths.startup_config_path)
        root2, _p, source = resolve_data_root_source(fresh, environ={})
        assert root2 == target.resolve()
        assert source == "startup"


def test_switch_conflict_requires_explicit_choice():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        target = root / "occupied"
        target.mkdir()
        (target / "songs.json").write_text("{}", encoding="utf-8")
        try:
            service.switch(str(target))
            assert False, "已有数据必须要求显式确认"
        except DataDirConflict as error:
            assert "songs.json" in error.existing_items
        assert not paths.startup_config_path.exists(), "冲突时不得写启动配置"

        result = service.switch(str(target), use_existing=True)
        assert result["used_existing"] is True
        assert json.loads(paths.startup_config_path.read_text(
            encoding="utf-8"))["data_root"] == str(target.resolve())


def test_switch_migrate_copies_data_and_keeps_original():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        _seed_current_data(paths)
        target = root / "migrated"
        result = service.switch(str(target), migrate=True)
        assert sorted(result["migrated"]) == sorted(
            ["songs.json", "events.jsonl", "settings.json",
             "tabs", "presets", "output"])
        assert (target / "songs.json").is_file()
        assert (target / "tabs" / "谱.png").read_bytes() == b"png"
        assert (target / "presets" / "p.json").is_file()
        assert (target / "output" / "poster.png").read_bytes() == b"out"
        # backups 不迁移；旧目录任何内容都不动
        assert not (target / "backups" / "old.json").exists()
        assert (paths.data_root / "songs.json").is_file()
        assert (paths.data_root / "tabs" / "谱.png").is_file()


def test_switch_migrate_refuses_target_with_data_and_rolls_back_nothing():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        _seed_current_data(paths)
        target = root / "occupied"
        target.mkdir()
        (target / "events.jsonl").write_text("exists", encoding="utf-8")
        try:
            service.switch(str(target), migrate=True)
            assert False, "目标已有数据时迁移必须拒绝"
        except DataDirConflict:
            pass
        assert not paths.startup_config_path.exists()
        assert (target / "events.jsonl").read_text(encoding="utf-8") == "exists"


def test_switch_validation_failure_never_writes_startup_config():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        for bad in ("", "relative/path", str(paths.data_root)):
            try:
                service.switch(bad)
                assert False, f"非法目标必须拒绝：{bad!r}"
            except DataDirValidationFailed:
                pass
        assert not paths.startup_config_path.exists()


def test_switch_unwritable_target_reports_unavailable_and_keeps_config():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        service, paths = _make_service(root)
        target = root / "broken"
        target.mkdir()
        # 标准子目录位置被同名文件占据 → 初始化必然失败
        (target / "tabs").write_text("not a dir", encoding="utf-8")
        try:
            service.switch(str(target))
            assert False, "初始化失败必须抛出 DataDirUnavailable"
        except DataDirUnavailable:
            pass
        assert not paths.startup_config_path.exists()


# ---------- HTTP 边界 ----------


def _http(app, method: str, path: str, payload: dict | None = None):
    from tests.test_api_contract import _request

    async def scenario():
        async with app.router.lifespan_context(app):
            return await _request(app, method, path, payload)

    return asyncio.run(scenario())


def _http_app(root: Path):
    from server.app import create_app

    config = AppConfig(
        PROJECT_ROOT, mode="test", data_root=root / "current",
        startup_config_path=root / "startup" / "startup.json",
    )
    return create_app(config)


def test_http_status_inspect_and_switch_flow():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        app = _http_app(root)

        status, body, _h = _http(app, "GET", "/api/settings/data-dir")
        assert status == 200
        assert body["source"] == "explicit"
        assert body["current"].endswith("current")

        target = root / "web 数据"
        status, body, _h = _http(
            app, "POST", "/api/settings/data-dir/inspect",
            {"path": str(target)})
        assert status == 200
        assert body["valid"] is True and body["will_initialize"] is True

        status, body, _h = _http(
            app, "POST", "/api/settings/data-dir", {"path": str(target)})
        assert status == 200
        assert body["ok"] is True and body["requires_restart"] is True
        assert (target / "tabs").is_dir()

        status, body, _h = _http(
            app, "POST", "/api/settings/data-dir", {"path": "relative/x"})
        assert status == 400
        assert body["error"]["code"] == "invalid_data_dir"


def test_http_switch_conflict_returns_409_with_items():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        app = _http_app(root)
        target = root / "occupied"
        target.mkdir()
        (target / "songs.json").write_text("{}", encoding="utf-8")

        status, body, _h = _http(
            app, "POST", "/api/settings/data-dir", {"path": str(target)})
        assert status == 409
        assert body["error"]["code"] == "data_dir_conflict"
        assert "songs.json" in body["error"]["details"]["existing_items"]

        status, body, _h = _http(
            app, "POST", "/api/settings/data-dir",
            {"path": str(target), "use_existing": True})
        assert status == 200
        assert body["used_existing"] is True


if __name__ == "__main__":
    failures = 0
    for name, func in sorted(list(globals().items())):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"✅ {name}")
            except Exception as error:  # noqa: BLE001
                failures += 1
                print(f"❌ {name}: {error!r}")
    sys.exit(1 if failures else 0)
