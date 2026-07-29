"""R0.10 本地服务监听、来源与会话令牌安全回归。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.api.handlers import SESSION_TOKEN_HEADER
from server.app import create_app
from server.config import (
    ALLOWED_ORIGINS_ENV,
    DEFAULT_DEVELOPMENT_ORIGINS,
    SESSION_TOKEN_ENV,
    AppConfig,
)


PROJECT = Path(__file__).resolve().parent.parent
TRUSTED_ORIGIN = "http://localhost:5173"
SESSION_TOKEN = "test-session-secret"


async def _request(app, method: str, path: str, payload=None,
                   headers: dict[str, str] | None = None,
                   content_type: str = "application/json",
                   client: tuple[str, int] = ("127.0.0.1", 1234)):
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

    request_headers = {"content-type": content_type, **(headers or {})}
    await app(
        {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": target.path,
            "raw_path": target.path.encode(), "query_string": target.query.encode(),
            "headers": [
                (key.lower().encode(), value.encode())
                for key, value in request_headers.items()
            ],
            "client": client, "server": ("127.0.0.1", 8000),
        },
        receive,
        send,
    )
    start = next(message for message in messages
                 if message["type"] == "http.response.start")
    response_headers = {
        key.decode().lower(): value.decode()
        for key, value in start.get("headers", [])
    }
    raw_body = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body")
    try:
        response_body = json.loads(raw_body)
    except json.JSONDecodeError:
        response_body = raw_body.decode("utf-8")
    return start["status"], response_body, response_headers


def _security_config(data_root: Path, **changes) -> AppConfig:
    options = {
        "project_root": PROJECT,
        "mode": "test",
        "data_root": data_root,
        "allowed_origins": (TRUSTED_ORIGIN,),
        "session_token": SESSION_TOKEN,
    }
    options.update(changes)
    return AppConfig(**options)


def test_service_host_accepts_only_loopback():
    for host in ("127.0.0.1", "::1", "localhost"):
        config = AppConfig(PROJECT, mode="test", data_root=PROJECT / ".test",
                           host=host)
        assert config.host == host
    bracketed = AppConfig(
        PROJECT, mode="test", data_root=PROJECT / ".test", host="[::1]")
    assert bracketed.host == "::1"
    for host in ("0.0.0.0", "::", "192.168.1.8", "workstation.local"):
        try:
            AppConfig(PROJECT, mode="test", data_root=PROJECT / ".test",
                      host=host)
            assert False, f"{host} 不得成为本地服务监听地址"
        except ValueError as error:
            assert "loopback" in str(error)


def test_cors_origins_are_explicit_and_local():
    config = AppConfig(
        PROJECT, mode="test", data_root=PROJECT / ".test",
        allowed_origins=(TRUSTED_ORIGIN, TRUSTED_ORIGIN),
    )
    assert config.allowed_origins == (TRUSTED_ORIGIN,)
    for origin in ("*", "https://example.com", "http://localhost:5173/path"):
        try:
            AppConfig(
                PROJECT, mode="test", data_root=PROJECT / ".test",
                allowed_origins=(origin,),
            )
            assert False, f"{origin} 不得进入 CORS 白名单"
        except ValueError:
            pass


def test_environment_has_safe_development_defaults_and_overrides():
    default = AppConfig.from_environment(mode="development", environ={})
    assert default.allowed_origins == DEFAULT_DEVELOPMENT_ORIGINS
    assert default.session_token is None
    configured = AppConfig.from_environment(
        mode="development",
        environ={
            ALLOWED_ORIGINS_ENV: "http://localhost:4173,http://127.0.0.1:4173",
            SESSION_TOKEN_ENV: SESSION_TOKEN,
        },
    )
    assert configured.allowed_origins == (
        "http://localhost:4173", "http://127.0.0.1:4173")
    assert configured.session_token == SESSION_TOKEN


def test_desktop_factory_requires_ephemeral_session_token():
    try:
        create_app(AppConfig(PROJECT, mode="desktop"))
        assert False, "desktop 模式无令牌时必须拒绝启动"
    except ValueError as error:
        assert "会话令牌" in str(error)
    try:
        create_app(AppConfig(
            PROJECT, mode="desktop", session_token="too-short"))
        assert False, "desktop 模式不得接受长度不足的会话令牌"
    except ValueError as error:
        assert "32" in str(error)


def test_controlled_launcher_has_no_host_override():
    from server.__main__ import _launch_options, _parser

    config = AppConfig(PROJECT, host="[::1]")
    options = _launch_options(config, port=8000, reload=True)
    assert options == {"host": "::1", "port": 8000, "reload": True}
    assert "--host" not in _parser().format_help()


def test_session_token_protects_writes_but_not_reads():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(_security_config(Path(raw) / "data"))
            async with app.router.lifespan_context(app):
                status, _, _ = await _request(app, "GET", "/api/settings")
                assert status == 200

                for token in (None, "wrong-token"):
                    headers = (
                        {"Origin": TRUSTED_ORIGIN, SESSION_TOKEN_HEADER: token}
                        if token else {"Origin": TRUSTED_ORIGIN}
                    )
                    status, body, response_headers = await _request(
                        app, "POST", "/api/settings",
                        {"appearanceMode": "dark"}, headers)
                    assert status == 401
                    assert body["error"]["code"] == "session_unauthorized"
                    assert body["error"]["request_id"]
                    assert response_headers["x-request-id"] == body["error"]["request_id"]
                    assert response_headers[
                        "access-control-allow-origin"] == TRUSTED_ORIGIN
                    assert SESSION_TOKEN not in json.dumps(body)

                status, body, response_headers = await _request(
                    app, "POST", "/api/settings",
                    {"appearanceMode": "dark"},
                    {
                        "Origin": TRUSTED_ORIGIN,
                        SESSION_TOKEN_HEADER: SESSION_TOKEN,
                    },
                )
                assert status == 200
                assert body["settings"]["appearanceMode"] == "dark"
                assert response_headers[
                    "access-control-allow-origin"] == TRUSTED_ORIGIN

    asyncio.run(scenario())


def test_untrusted_browser_origin_cannot_write():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(_security_config(Path(raw) / "data"))
            async with app.router.lifespan_context(app):
                status, body, _ = await _request(
                    app, "POST", "/api/settings",
                    {"appearanceMode": "dark"},
                    {
                        "Origin": "https://evil.example",
                        SESSION_TOKEN_HEADER: SESSION_TOKEN,
                    },
                    content_type="text/plain",
                )
                assert status == 403
                assert body["error"]["code"] == "origin_forbidden"
                status, settings, _ = await _request(app, "GET", "/api/settings")
                assert status == 200
                assert settings["appearanceMode"] != "dark"

    asyncio.run(scenario())


def test_non_loopback_client_is_rejected_even_if_socket_is_misbound():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(AppConfig(
                PROJECT,
                mode="development",
                data_root=Path(raw) / "data",
                allowed_origins=(TRUSTED_ORIGIN,),
            ))
            async with app.router.lifespan_context(app):
                status, body, _ = await _request(
                    app, "GET", "/api/health",
                    client=("192.168.1.50", 50000),
                )
                assert status == 403
                assert body["error"]["code"] == "local_client_required"

    asyncio.run(scenario())


def test_cors_preflight_exposes_only_trusted_origin_and_headers():
    async def scenario():
        with tempfile.TemporaryDirectory() as raw:
            app = create_app(_security_config(Path(raw) / "data"))
            trusted_headers = {
                "Origin": TRUSTED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": SESSION_TOKEN_HEADER,
            }
            status, _, headers = await _request(
                app, "OPTIONS", "/api/settings", headers=trusted_headers)
            assert status == 200
            assert headers["access-control-allow-origin"] == TRUSTED_ORIGIN
            assert SESSION_TOKEN_HEADER.lower() in headers[
                "access-control-allow-headers"].lower()

            denied_headers = {
                **trusted_headers,
                "Origin": "https://evil.example",
            }
            status, _, headers = await _request(
                app, "OPTIONS", "/api/settings", headers=denied_headers)
            assert status == 400
            assert "access-control-allow-origin" not in headers

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
