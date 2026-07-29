"""R0.6 AppConfig/AppPaths 与应用工厂独立回归。"""
from __future__ import annotations

import json
import asyncio
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


def test_factory_does_not_write_data_root():
    from server.app import create_app
    with tempfile.TemporaryDirectory() as raw:
        data_root = Path(raw) / "not-created"
        app = create_app(AppConfig(Path(__file__).resolve().parent.parent,
                                   mode="test", data_root=data_root))
        assert app.state.paths.data_root == data_root.resolve()
        assert not data_root.exists()
        assert not hasattr(app.state, "context")


def test_lifespan_builds_and_releases_context():
    from server.app import create_app
    from server.ports.repositories import RepositoryClosed

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            data_root = Path(raw) / "data"
            app = create_app(AppConfig(Path(__file__).resolve().parent.parent,
                                       mode="test", data_root=data_root))
            async with app.router.lifespan_context(app):
                context = app.state.context
                assert context.paths.data_root == data_root.resolve()
                song_repository = context.song_repository
                settings_repository = context.settings_repository
                event_store = context.event_store
                preset_repository = context.preset_repository
                assert context.export_job_manager is app.state.export_jobs
                assert (data_root / "tabs").is_dir()
                assert (data_root / "presets").is_dir()
            assert not hasattr(app.state, "context")
            for operation in (song_repository.load, settings_repository.load,
                              preset_repository.list, event_store.flush):
                try:
                    operation()
                    assert False, "lifespan 退出后 Repository 必须关闭"
                except RepositoryClosed:
                    pass

    asyncio.run(scenario())


def test_two_apps_have_distinct_context_and_mutable_state():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = Path(__file__).resolve().parent.parent
            app_a = create_app(AppConfig(project, mode="test", data_root=base / "a"))
            app_b = create_app(AppConfig(project, mode="test", data_root=base / "b"))
            async with app_a.router.lifespan_context(app_a):
                async with app_b.router.lifespan_context(app_b):
                    a = app_a.state.context
                    b = app_b.state.context
                    assert a is not b
                    assert a.paths.data_root != b.paths.data_root
                    assert a.song_repository is not b.song_repository
                    assert a.settings_repository is not b.settings_repository
                    assert a.export_job_manager is not b.export_job_manager
                    a.export_job_manager["only-a"] = {"status": "queued"}
                    assert "only-a" not in b.export_job_manager

    asyncio.run(scenario())


def test_nested_lifespans_http_writes_stay_in_request_app():
    from server.app import create_app

    async def request(app, method: str, path: str, payload=None):
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b""
        sent = False
        messages = []

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        headers = [(b"content-type", b"application/json")] if payload is not None else []
        await app({"type": "http", "asgi": {"version": "3.0"},
                   "http_version": "1.1", "method": method, "scheme": "http",
                   "path": path, "raw_path": path.encode(), "query_string": b"",
                   "headers": headers, "client": ("test", 1), "server": ("test", 80)},
                  receive, send)
        status = next(message["status"] for message in messages
                      if message["type"] == "http.response.start")
        response_body = b"".join(message.get("body", b"") for message in messages
                                 if message["type"] == "http.response.body")
        return status, json.loads(response_body) if response_body else None

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = Path(__file__).resolve().parent.parent
            app_a = create_app(AppConfig(project, mode="test", data_root=base / "a"))
            app_b = create_app(AppConfig(project, mode="test", data_root=base / "b"))
            async with app_a.router.lifespan_context(app_a):
                async with app_b.router.lifespan_context(app_b):
                    status, _ = await request(app_a, "POST", "/api/songs/add",
                                              {"title": "只属于 A"})
                    assert status == 200
                    status, _ = await request(app_a, "POST", "/api/presets",
                                              {"id": "only-a", "name": "A 预设"})
                    assert status == 200
                    status, songs_b = await request(app_b, "GET", "/api/songs/list")
                    assert status == 200
                    status, presets_b = await request(app_b, "GET", "/api/presets")
                    assert status == 200
                    assert all(song["title"] != "只属于 A" for song in songs_b["songs"])
                    assert all(item["id"] != "only-a" for item in presets_b)

                    assert (base / "a" / "songs.json").is_file()
                    assert not (base / "b" / "songs.json").exists()
                    assert (base / "a" / "events.jsonl").is_file()
                    assert not (base / "b" / "events.jsonl").exists()
                    assert (base / "a" / "presets" / "only-a" / "preset.json").is_file()
                    assert not (base / "b" / "presets" / "only-a").exists()

            reopened = create_app(AppConfig(project, mode="test", data_root=base / "a"))
            async with reopened.router.lifespan_context(reopened):
                status, songs = await request(reopened, "GET", "/api/songs/list")
                assert status == 200
                assert any(song["title"] == "只属于 A" for song in songs["songs"])
                status, presets = await request(reopened, "GET", "/api/presets")
                assert status == 200
                assert any(item["id"] == "only-a" for item in presets)

    asyncio.run(scenario())


def test_corrupt_song_data_blocks_startup_without_publishing_context():
    from server.app import create_app
    from server.ports.repositories import RepositoryCorrupt

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            data_root = Path(raw)
            (data_root / "songs.json").write_text(
                json.dumps({"version": 999, "songs": []}), encoding="utf-8")
            app = create_app(AppConfig(Path(__file__).resolve().parent.parent,
                                       mode="test", data_root=data_root))
            try:
                async with app.router.lifespan_context(app):
                    assert False, "损坏数据必须阻止启动"
            except RepositoryCorrupt:
                pass
            assert not hasattr(app.state, "context")

    asyncio.run(scenario())


def test_inconsistent_preset_manifest_blocks_startup():
    from server.app import create_app
    from server.ports.repositories import RepositoryError

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            data_root = Path(raw)
            presets = data_root / "presets"
            presets.mkdir()
            (presets / "manifest.json").write_text(json.dumps({
                "missing": {"name": "缺失内容", "layout_id": "grid-wrap",
                            "is_default": False, "created_at": "", "updated_at": ""},
            }), encoding="utf-8")
            app = create_app(AppConfig(Path(__file__).resolve().parent.parent,
                                       mode="test", data_root=data_root))
            try:
                async with app.router.lifespan_context(app):
                    assert False, "Preset manifest 与内容不一致必须阻止启动"
            except RepositoryError:
                pass
            assert not hasattr(app.state, "context")

    asyncio.run(scenario())


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
