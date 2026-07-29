"""R0.8 API 契约基础切片的独立回归测试。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

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


async def _request(app, method: str, path: str, payload: dict | None = None,
                   headers: dict[str, str] | None = None):
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
                "method": method, "scheme": "http", "path": path,
                "raw_path": path.encode(), "query_string": b"",
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
