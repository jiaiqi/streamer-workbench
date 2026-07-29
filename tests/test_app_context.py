"""R0.6 AppConfig/AppPaths 与应用工厂独立回归。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import AppConfig, build_app_paths, platform_data_root


def test_paths_are_pure_and_derived_from_one_root():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        project = root / "project"
        data = root / "用户 数据"
        config = AppConfig(project_root=project, mode="test", data_root=data)
        paths = build_app_paths(config, environ={}, platform="darwin", home=root)
        data = data.resolve()
        project = project.resolve()
        assert paths.data_root == data
        assert paths.songs_json == data / "songs.json"
        assert paths.tabs_dir == data / "tabs"
        assert paths.themes_dir == project / "themes"
        assert not project.exists() and not data.exists()


def test_data_root_priority_explicit_env_startup_development_platform():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        project = root / "project"
        startup = root / "config" / "startup.json"
        startup.parent.mkdir()
        startup.write_text(json.dumps({"data_root": str(root / "startup-data")}),
                           encoding="utf-8")
        env = {"STREAMER_WORKBENCH_DATA_DIR": str(root / "env-data")}

        explicit = AppConfig(project, data_root=root / "explicit", startup_config_path=startup)
        assert build_app_paths(explicit, environ=env).data_root == (root / "explicit").resolve()
        env_config = AppConfig(project, startup_config_path=startup)
        assert build_app_paths(env_config, environ=env).data_root == (root / "env-data").resolve()
        assert build_app_paths(env_config, environ={}).data_root == (root / "startup-data").resolve()
        startup.unlink()
        assert build_app_paths(env_config, environ={}).data_root == project.resolve() / "data"
        desktop = AppConfig(project, mode="desktop", startup_config_path=startup)
        assert build_app_paths(desktop, environ={}, platform="darwin", home=root).data_root == (
            root.resolve() / "Library" / "Application Support" / "streamer-workbench")


def test_platform_defaults_can_be_mocked():
    home = Path("/tmp/mock-home")
    assert platform_data_root("win32", {"APPDATA": "/tmp/appdata"}, home) == (
        Path("/tmp/appdata").resolve() / "streamer-workbench")
    assert platform_data_root("linux", {"XDG_DATA_HOME": "/tmp/xdg"}, home) == (
        Path("/tmp/xdg").resolve() / "streamer-workbench")
    assert platform_data_root("linux", {}, home) == (
        home.resolve() / ".local" / "share" / "streamer-workbench")


def test_test_mode_requires_explicit_data_root():
    try:
        AppConfig(Path("/tmp/project"), mode="test")
        assert False, "test 模式不得回退到真实用户目录"
    except ValueError as error:
        assert "data_root" in str(error)


def _run():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    failures = []
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
        except Exception as error:
            failures.append((test.__name__, error))
            print(f"  ❌ {test.__name__}: {error}")
    print(f"\n{len(tests) - len(failures)} passed, {len(failures)} failed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    _run()
