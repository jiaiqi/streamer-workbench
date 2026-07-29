"""R0.7/R0.11 PresetApplicationService 与 HTTP 垂直切片测试。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

from core.data.presets import Preset
from server.app import create_app
from server.config import AppConfig
from server.ports.repositories import BackupPolicy, RepositoryConflict
from server.repositories.presets import FilePresetRepository
from server.services.presets import (
    PresetApplicationService,
    PresetNotFound,
    PresetProtected,
    PresetValidationFailed,
)


PROJECT = Path(__file__).resolve().parent.parent


def _service(root: Path):
    repository = FilePresetRepository(
        root / "presets", BackupPolicy(root / "backups" / "presets"))
    return repository, PresetApplicationService(preset_repository=repository)


def test_service_crud_preserves_server_owned_identity_time_and_default_state():
    with tempfile.TemporaryDirectory() as raw:
        repository, service = _service(Path(raw))
        default = service.save({"id": "_default", "name": "默认预设"}).preset
        scene = service.save({
            "id": "scene", "name": "直播场景", "is_default": True,
            "params": {"margin": 52},
        }).preset
        assert default.is_default is True
        assert scene.is_default is False

        service.set_default("scene")
        edited = service.save({
            "id": "scene", "name": "直播场景 v2", "is_default": False,
            "created_at": "2000-01-01T00:00:00+00:00",
            "params": {"margin": 64},
        }).preset
        assert edited.is_default is True
        assert edited.created_at == scene.created_at
        assert edited.params == {"margin": 64}
        try:
            service.delete("scene")
            assert False, "当前默认预设必须受保护"
        except PresetProtected:
            pass

        service.set_default("_default")
        duplicated = service.duplicate("scene", name="场景副本").preset
        assert duplicated.id != "scene"
        assert duplicated.name == "场景副本"
        assert duplicated.is_default is False
        service.delete("scene")
        assert [item.id for item in service.list()] == [duplicated.id, "_default"]
        repository.close()


def test_service_rejects_invalid_queries_and_missing_targets():
    with tempfile.TemporaryDirectory() as raw:
        repository, service = _service(Path(raw))
        for payload in (
            {"name": "坏结构", "song_query": "not-an-object"},
            {"name": "坏 ID", "song_query": {"custom_ids": ["title"]}},
            {"schema_version": 1, "name": "旧 Schema"},
            {"name": "   "},
        ):
            try:
                service.save(payload)
                assert False, "非法预设不得保存"
            except PresetValidationFailed:
                pass
        for operation in (
            lambda: service.get("missing"),
            lambda: service.duplicate("missing"),
            lambda: service.delete("missing"),
            lambda: service.set_default("missing"),
        ):
            try:
                operation()
                assert False, "缺失预设必须返回稳定业务错误"
            except PresetNotFound:
                pass
        repository.close()


def test_concurrent_create_same_id_uses_missing_revision_cas():
    with tempfile.TemporaryDirectory() as raw:
        repository, _ = _service(Path(raw))
        barrier = threading.Barrier(2)

        class BarrierRepository:
            def get(self, preset_id):
                snapshot = repository.get(preset_id)
                if preset_id == "race" and snapshot is None:
                    barrier.wait()
                return snapshot

            def save(self, preset, *, expected_revision):
                return repository.save(
                    preset, expected_revision=expected_revision)

        services = [
            PresetApplicationService(preset_repository=BarrierRepository()),
            PresetApplicationService(preset_repository=BarrierRepository()),
        ]
        successes = []
        conflicts = []

        def create(service, name):
            try:
                successes.append(service.save(
                    {"id": "race", "name": name}).preset.name)
            except RepositoryConflict as error:
                conflicts.append(error)

        workers = [
            threading.Thread(target=create, args=(services[0], "A")),
            threading.Thread(target=create, args=(services[1], "B")),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert repository.get("race").value.name == successes[0]
        repository.close()


def test_router_delegates_all_preset_writes_to_application_service():
    import server.routers.presets as router

    class RecordingService:
        def __init__(self):
            self.calls = []

        def save(self, payload):
            self.calls.append(("save", payload))
            preset = Preset(id="delegated", name="委托预设", updated_at="now")
            return SimpleNamespace(preset=preset)

        def duplicate(self, preset_id, *, name=""):
            self.calls.append(("duplicate", preset_id, name))
            return SimpleNamespace(preset=Preset(id="copy", name=name or "副本"))

        def delete(self, preset_id):
            self.calls.append(("delete", preset_id))

        def set_default(self, preset_id):
            self.calls.append(("default", preset_id))
            return SimpleNamespace(preset_id=preset_id)

    service = RecordingService()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(
            context=SimpleNamespace(preset_service=service))),
        state=SimpleNamespace(),
    )
    assert router.api_presets_save({"name": "委托预设"}, request)["id"] == "delegated"
    assert router.api_presets_duplicate(
        "source", request, {"name": "复制名"})["id"] == "copy"
    assert router.api_presets_delete("source", request) == {"ok": True}
    assert router.api_presets_set_default(
        "source", request) == {"ok": True, "id": "source"}
    assert [call[0] for call in service.calls] == [
        "save", "duplicate", "delete", "default"]


def test_real_http_preset_crud_default_and_error_envelopes():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(
                PROJECT, mode="test", data_root=Path(raw) / "data"))
            async with app.router.lifespan_context(app):
                status, default = await _request(
                    app, "POST", "/api/presets",
                    {"id": "_default", "name": "默认预设"})
                assert status == 200 and default["id"] == "_default"
                status, scene = await _request(
                    app, "POST", "/api/presets",
                    {"id": "scene", "name": "直播场景",
                     "params": {"margin": 52}})
                assert status == 200 and scene["id"] == "scene"

                status, switched = await _request(
                    app, "POST", "/api/presets/scene/default")
                assert status == 200 and switched["id"] == "scene"
                status, protected = await _request(
                    app, "DELETE", "/api/presets/scene")
                assert status == 400
                assert protected["error"]["code"] == "default_preset_protected"
                assert protected["error"]["request_id"].startswith("req_")

                status, duplicate = await _request(
                    app, "POST", "/api/presets/scene/duplicate",
                    {"name": "直播场景副本"})
                assert status == 200 and duplicate["name"] == "直播场景副本"
                status, missing = await _request(
                    app, "POST", "/api/presets/missing/default")
                assert status == 404
                assert missing["error"]["code"] == "preset_not_found"
                for invalid in (
                    {"schema_version": 1, "name": "旧 Schema"},
                    {"name": ""},
                ):
                    status, body = await _request(
                        app, "POST", "/api/presets", invalid)
                    assert status == 400
                    assert body["error"]["code"] == "invalid_preset"

    asyncio.run(scenario())


def test_app_context_exposes_preset_service_bound_to_repository():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(
                PROJECT, mode="test", data_root=Path(raw) / "data"))
            async with app.router.lifespan_context(app):
                context = app.state.context
                saved = context.preset_service.save(
                    {"id": "context", "name": "上下文预设"}).preset
                assert context.preset_repository.get(saved.id).value.name == "上下文预设"

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
        "headers": headers, "client": ("test", 1), "server": ("test", 80),
    }, receive, send)
    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    response = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body")
    return status, json.loads(response) if response else None


def _run():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"  ✅ {test.__name__}")
    print(f"\n{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    _run()
