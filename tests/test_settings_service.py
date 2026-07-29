"""R0.7 SettingsApplicationService 与外观设置契约测试。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

from server.app import create_app
from server.config import AppConfig
from server.deps import default_settings
from server.ports.repositories import BackupPolicy, RepositoryConflict
from server.repositories.settings import FileSettingsRepository
from server.services.settings import (
    SettingsApplicationService,
    SettingsValidationFailed,
)


PROJECT = Path(__file__).resolve().parent.parent


def _service(root: Path):
    settings_path = root / "settings.json"
    repository = FileSettingsRepository(
        settings_path,
        BackupPolicy(root / "backups" / "settings"),
        defaults={
            "output_dir": str(root / "output"),
            "default_canvas": "抖音全屏 9:20",
            "default_theme": "海洋柔光",
            "font_path": str(root / "font.ttf"),
            "backup_count": 20,
            "render_threads": 1,
            "appearanceMode": "system",
            "applicationAccentId": "bambooMoon",
        },
    )
    return repository, SettingsApplicationService(
        settings_repository=repository)


def test_service_updates_partial_settings_and_preserves_unknown_fields():
    with tempfile.TemporaryDirectory() as raw:
        repository, service = _service(Path(raw))
        first = repository.load()
        document = first.value
        document["future_setting"] = {"enabled": True}
        repository.save(document, expected_revision=first.revision)

        updated = service.update({
            "appearanceMode": "dark",
            "applicationAccentId": "rainSky",
            "render_threads": 2,
        })
        assert updated["appearanceMode"] == "dark"
        assert updated["applicationAccentId"] == "rainSky"
        assert updated["render_threads"] == 2
        assert updated["future_setting"] == {"enabled": True}
        repository.close()


def test_service_falls_back_for_unknown_appearance_values_without_touching_poster_theme():
    with tempfile.TemporaryDirectory() as raw:
        repository, service = _service(Path(raw))
        updated = service.update({
            "appearanceMode": "sepia",
            "applicationAccentId": "untrusted-hex",
            "default_theme": "海洋柔光",
        })
        assert updated["appearanceMode"] == "system"
        assert updated["applicationAccentId"] == "bambooMoon"
        assert updated["default_theme"] == "海洋柔光"
        repository.close()


def test_service_rejects_invalid_operational_limits():
    with tempfile.TemporaryDirectory() as raw:
        repository, service = _service(Path(raw))
        for payload in (
            {"backup_count": -1},
            {"backup_count": 101},
            {"render_threads": 0},
            {"render_threads": 17},
            {"output_dir": None},
        ):
            try:
                service.update(payload)
                assert False, "非法设置不得保存"
            except SettingsValidationFailed:
                pass
        repository.close()


def test_concurrent_updates_use_repository_revision_cas():
    with tempfile.TemporaryDirectory() as raw:
        repository, _ = _service(Path(raw))
        barrier = threading.Barrier(2)

        class BarrierRepository:
            def load(self):
                snapshot = repository.load()
                barrier.wait()
                return snapshot

            def save(self, settings, *, expected_revision):
                return repository.save(
                    settings, expected_revision=expected_revision)

        services = [
            SettingsApplicationService(settings_repository=BarrierRepository()),
            SettingsApplicationService(settings_repository=BarrierRepository()),
        ]
        successes = []
        conflicts = []

        def update(service, accent):
            try:
                successes.append(service.update({
                    "applicationAccentId": accent,
                })["applicationAccentId"])
            except RepositoryConflict as error:
                conflicts.append(error)

        workers = [
            threading.Thread(target=update, args=(services[0], "rainSky")),
            threading.Thread(target=update, args=(services[1], "rouge")),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert service_value(repository)["applicationAccentId"] == successes[0]
        repository.close()


def service_value(repository):
    return SettingsApplicationService(
        settings_repository=repository).get()


def test_router_delegates_reads_and_writes_to_application_service():
    import server.routers.settings as router

    class RecordingService:
        def __init__(self):
            self.changes = []

        def get(self):
            return {"applicationAccentId": "bambooMoon"}

        def update(self, changes):
            self.changes.append(changes)
            return {**changes, "appearanceMode": "system"}

    service = RecordingService()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        context=SimpleNamespace(settings_service=service))))
    assert router.api_settings_get(request)["applicationAccentId"] == "bambooMoon"
    result = router.api_settings_update(
        request, {"applicationAccentId": "wisteria"})
    assert result["settings"]["applicationAccentId"] == "wisteria"
    assert service.changes == [{"applicationAccentId": "wisteria"}]


def test_http_persists_appearance_and_exposes_context_service():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(
                PROJECT, mode="test", data_root=Path(raw) / "data"))
            async with app.router.lifespan_context(app):
                context = app.state.context
                assert context.settings_service.get() == default_settings(context.paths)
                status, body = await _request(app, "POST", "/api/settings", {
                    "appearanceMode": "dark",
                    "applicationAccentId": "amber",
                })
                assert status == 200
                assert body["settings"]["appearanceMode"] == "dark"
                assert body["settings"]["applicationAccentId"] == "amber"
                status, body = await _request(app, "GET", "/api/settings")
                assert status == 200
                assert body["appearanceMode"] == "dark"
                assert body["applicationAccentId"] == "amber"

    asyncio.run(scenario())


async def _request(app, method: str, path: str, payload=None):
    body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None else b"")
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
    await app({
        "type": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": path, "raw_path": path.encode("utf-8"), "query_string": b"",
        "headers": headers, "client": ("test", 123), "server": ("test", 80),
    }, receive, send)
    start = next(message for message in messages
                 if message["type"] == "http.response.start")
    raw_body = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body")
    return start["status"], json.loads(raw_body)


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
