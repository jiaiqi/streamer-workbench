"""R0.8 API 契约基础切片的独立回归测试。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.api.errors import ApiError, map_repository_error
from server.config import AppConfig
from server.ports.repositories import (
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryNotFound,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_error_envelope_omits_absent_optional_fields():
    assert ApiError("invalid", "请求无效").envelope() == {
        "error": {"code": "invalid", "message": "请求无效", "details": {}}
    }


def test_repository_error_mapping_is_stable_and_framework_independent():
    cases = (
        (RepositoryNotFound("missing"), 404, "repository_not_found"),
        (RepositoryConflict("stale"), 409, "repository_conflict"),
        (RepositoryCorrupt("broken"), 500, "repository_corrupt"),
        (RepositoryRecoveryRequired("recover"), 503, "repository_recovery_required"),
        (RepositoryClosed("closed"), 503, "repository_closed"),
        (RepositoryUnavailable("busy"), 503, "repository_unavailable"),
        (RuntimeError("secret"), 500, "internal_error"),
    )
    for error, expected_status, expected_code in cases:
        status, api_error = map_repository_error(error)
        assert status == expected_status
        assert api_error.code == expected_code
    _, unknown = map_repository_error(RuntimeError("do not leak"))
    assert "do not leak" not in json.dumps(unknown.envelope(), ensure_ascii=False)


def test_event_openapi_uses_named_request_and_response_models():
    from server.app import create_app

    with tempfile.TemporaryDirectory() as raw:
        app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
        schema = app.openapi()
    get_operation = schema["paths"]["/api/events"]["get"]
    post_operation = schema["paths"]["/api/events/report"]["post"]
    assert get_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/EventsResponse"
    )
    assert post_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/EventReportRequest"
    )
    assert post_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/EventReportResponse"
    )
    request_schema = schema["components"]["schemas"]["EventReportRequest"]
    assert request_schema["additionalProperties"] is False
    assert set(request_schema["properties"]["type"]["enum"]) == {
        "queue_added", "song_sung", "practice_logged"
    }


def test_songs_openapi_uses_named_models_for_id_and_title_compat_routes():
    from server.app import create_app

    with tempfile.TemporaryDirectory() as raw:
        app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
        schema = app.openapi()
    id_patch = schema["paths"]["/api/songs/{song_id}"]["patch"]
    legacy_update = schema["paths"]["/api/songs/update"]["post"]
    assert id_patch["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SongEditableFields"
    )
    assert id_patch["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SongUpdateResponse"
    )
    assert legacy_update["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SongLegacyUpdateRequest"
    )
    assert schema["components"]["schemas"]["SongEditableFields"]["additionalProperties"] is False


def test_secondary_openapi_uses_named_body_query_and_response_models():
    from server.app import create_app

    with tempfile.TemporaryDirectory() as raw:
        app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
        schema = app.openapi()
    settings = schema["paths"]["/api/settings"]["post"]
    presets = schema["paths"]["/api/presets"]["post"]
    render = schema["paths"]["/api/render"]["get"]
    export = schema["paths"]["/api/export"]["post"]
    assert settings["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SettingsUpdateRequest"
    )
    assert presets["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PresetRequest"
    )
    assert export["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ExportResponse"
    )
    assert {item["name"] for item in render["parameters"]} >= {"theme", "layout", "canvas", "t"}
    assert schema["components"]["schemas"]["SettingsUpdateRequest"]["additionalProperties"] is False
    assert schema["components"]["schemas"]["PresetRequest"]["additionalProperties"] is False


async def _request(app, method: str, path: str, payload: dict | None = None,
                   headers: dict[str, str] | None = None):
    target = urlsplit(path)
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

    try:
        await app(
            {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": target.path,
                "raw_path": target.path.encode(), "query_string": target.query.encode(),
                "headers": [
                    (key.lower().encode(), value.encode())
                    for key, value in ({"content-type": "application/json"} | (headers or {})).items()
                ],
                "client": ("test", 1), "server": ("test", 80),
            },
            receive,
            send,
        )
    except Exception:
        # Starlette ServerErrorMiddleware 在发送测试响应后仍会重新抛出，便于测试客户端配置。
        if not any(message["type"] == "http.response.start" for message in messages):
            raise
    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    response_start = next(message for message in messages
                          if message["type"] == "http.response.start")
    response_headers = {
        key.decode().lower(): value.decode()
        for key, value in response_start.get("headers", [])
    }
    response_body = b"".join(message.get("body", b"") for message in messages
                             if message["type"] == "http.response.body")
    return status, json.loads(response_body), response_headers


def test_event_report_rejects_unknown_fields_before_business_logic():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                status, body, headers = await _request(
                    app,
                    "POST",
                    "/api/events/report",
                    {"type": "queue_added", "unexpected": True},
                )
                assert status == 422
                assert body["error"]["code"] == "validation_error"
                assert body["error"]["details"]["issues"][0]["type"] == "extra_forbidden"
                assert body["error"]["request_id"] == headers["x-request-id"]

    asyncio.run(scenario())


def test_songs_reject_unknown_fields_and_keep_title_compatibility_routes():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                status, body, _ = await _request(
                    app, "POST", "/api/songs/add",
                    {"title": "契约测试歌", "unexpected": True},
                )
                assert status == 422
                assert body["error"]["code"] == "validation_error"

                status, created, _ = await _request(
                    app, "POST", "/api/songs/add", {"title": "契约测试歌"})
                assert status == 200
                assert created["song"]["title"] == "契约测试歌"

                status, updated, _ = await _request(
                    app, "POST", "/api/songs/update",
                    {"title": "契约测试歌", "fields": {"title": "兼容路径新名"}},
                )
                assert status == 200
                assert updated["song"]["id"] == created["song"]["id"]
                assert updated["song"]["title"] == "兼容路径新名"

                status, changed, _ = await _request(
                    app, "POST", "/api/songs/status",
                    {"title": "兼容路径新名", "status": "active"},
                )
                assert status == 200
                assert changed["status"] == "active"

    asyncio.run(scenario())


def test_settings_and_presets_are_typed_without_losing_compatible_fields():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                status, body, _ = await _request(
                    app, "POST", "/api/settings", {"unknown_setting": True})
                assert status == 422 and body["error"]["code"] == "validation_error"

                status, body, _ = await _request(
                    app, "POST", "/api/settings", {"render_threads": 2})
                assert status == 200 and body["settings"]["render_threads"] == 2

                status, body, _ = await _request(
                    app, "POST", "/api/presets",
                    {"id": "contract-preset", "name": "契约预设", "unexpected": True},
                )
                assert status == 422 and body["error"]["code"] == "validation_error"

                status, body, _ = await _request(
                    app, "POST", "/api/presets",
                    {
                        "id": "contract-preset", "name": "契约预设",
                        "song_query": {"status": "active", "custom_ids": []},
                        "params": {"margin": 52},
                    },
                )
                assert status == 200 and body["id"] == "contract-preset"
                status, preset, _ = await _request(
                    app, "GET", "/api/presets/contract-preset")
                assert status == 200
                assert preset["song_query"]["status"] == "active"
                assert preset["params"] == {"margin": 52}

                status, body, _ = await _request(app, "GET", "/api/presets/missing")
                assert status == 404 and body["error"]["code"] == "preset_not_found"

    asyncio.run(scenario())


def test_render_and_export_query_models_reject_unknown_fields_before_services():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                for path in (
                    "/api/render?theme=missing&unexpected=1",
                    "/api/export?theme=missing&unexpected=1",
                    "/api/export/batch?unexpected=1",
                ):
                    status, body, _ = await _request(
                        app, "GET" if path.startswith("/api/render") else "POST", path)
                    assert status == 422
                    assert body["error"]["code"] == "validation_error"

                # 旧图片缓存字段 t 仍可通过边界校验，随后进入原有主题 404 语义。
                status, body, _ = await _request(
                    app, "GET", "/api/render?theme=missing&t=123")
                assert status == 404 and body["error"]["code"] == "theme_not_found"

    asyncio.run(scenario())


def test_export_router_delegates_validated_commands_to_application_service():
    from server.app import create_app
    from server.services.export import ExportSpec

    class RecordingExportService:
        def __init__(self):
            self.specs = []

        def export_one(self, spec):
            self.specs.append(spec)
            return SimpleNamespace(
                path=Path("/tmp/delegated.png"),
                filename="delegated.png",
                duration_ms=1.5,
            )

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                service = RecordingExportService()
                app.state.context.export_service = service
                status, body, _ = await _request(
                    app,
                    "POST",
                    "/api/export?theme=%E6%B5%B7%E6%B4%8B%E6%9F%94%E5%85%89"
                    "&layout=grid-wrap&canvas=%E6%A0%87%E5%87%86%209%3A16"
                    "&page=2&margin=52",
                )
                assert status == 200
                assert body["filename"] == "delegated.png"
                assert service.specs == [ExportSpec(
                    theme="海洋柔光",
                    page=2,
                    canvas="标准 9:16",
                    avoid=False,
                    layout="grid-wrap",
                    parameters={
                        "margin": 52,
                        "font_song": None,
                        "row_h": None,
                        "sec_gap": None,
                    },
                )]

    asyncio.run(scenario())


def test_export_application_service_completes_real_http_vertical_slice():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                status, body, _ = await _request(
                    app,
                    "POST",
                    "/api/export?theme=%E6%B5%B7%E6%B4%8B%E6%9F%94%E5%85%89"
                    "&layout=grid-wrap&canvas=%E6%A0%87%E5%87%86%209%3A16",
                )
                assert status == 200
                assert Path(body["path"]).is_file()
                events = app.state.context.event_store.tail(
                    limit=1, event_type="poster_exported")
                assert len(events) == 1
                assert events[0]["meta"]["snapshot_id"].startswith("export_")
                assert len(events[0]["meta"]["document_ids"]) == 1

    asyncio.run(scenario())


def test_request_id_is_propagated_and_invalid_value_is_replaced():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))
            async with app.router.lifespan_context(app):
                status, body, headers = await _request(
                    app, "GET", "/api/missing", headers={"x-request-id": "client_req-1"})
                assert status == 404
                assert headers["x-request-id"] == "client_req-1"
                assert body["error"]["request_id"] == "client_req-1"
                assert body["error"]["code"] == "not_found"

                _, body, headers = await _request(
                    app, "GET", "/api/missing", headers={"x-request-id": "bad id\nvalue"})
                assert headers["x-request-id"].startswith("req_")
                assert body["error"]["request_id"] == headers["x-request-id"]

    asyncio.run(scenario())


def test_unhandled_error_uses_safe_envelope_without_leaking_exception():
    from server.app import create_app

    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=Path(raw)))

            @app.get("/api/test-unhandled")
            def fail():
                raise RuntimeError("sensitive implementation detail")

            async with app.router.lifespan_context(app):
                status, body, headers = await _request(app, "GET", "/api/test-unhandled")
                assert status == 500
                assert body["error"]["code"] == "internal_error"
                assert body["error"]["request_id"] == headers["x-request-id"]
                assert "sensitive" not in json.dumps(body, ensure_ascii=False)

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
