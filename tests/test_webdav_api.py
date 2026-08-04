"""M2.2 WebDAV HTTP API 端到端测试。

策略：
- 用 Python 内置 http.server 起一个轻量 mock WebDAV（基本 PROPFIND / MKCOL / PUT / GET / DELETE）
- WebDavClient 真的发 HTTP 请求给 mock（不走 mock urllib），验证全链路
- 覆盖 6 个端点：config GET/PUT/clear、test、test-saved、list、push、pull
- 错误路径：未配置调用 list/pull/push、错主密码、错 URL、远端 401 等
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ── Mock WebDAV 服务 ──────────────────────────────────────────────

# 内存存储：path -> bytes 或 {is_dir: True}
_storage: dict[str, bytes | dict] = {}
_auth_credentials: dict[str, str] = {}  # username -> password
_accept_anon: bool = True


def _reset_storage():
    _storage.clear()
    _auth_credentials.clear()
    global _accept_anon
    _accept_anon = True


def _put(path: str, data: bytes):
    # 自动建父目录
    parts = path.strip("/").split("/")
    cur = _storage
    for p in parts[:-1]:
        if p not in cur:
            cur[p] = {"__children__": {}}
        cur = cur[p]["__children__"]
    cur[parts[-1]] = data


def _get_storage_path(path: str):
    parts = path.strip("/").split("/")
    if not parts or parts == [""]:
        return _storage
    cur = _storage
    for p in parts:
        if isinstance(cur, dict) and p in cur and isinstance(cur[p], dict) and "__children__" in cur[p]:
            cur = cur[p]["__children__"]
        elif isinstance(cur, dict) and p in cur and isinstance(cur[p], bytes):
            return cur[p]
        else:
            return None
    return cur


def _listdir(path: str) -> list[tuple[str, bool, int, str]]:
    """返回 [(name, is_dir, size, last_modified), ...]"""
    cur = _get_storage_path(path)
    if cur is None or not isinstance(cur, dict):
        return []
    out = []
    for name, value in cur.items():
        if name == "__children__":
            continue
        if isinstance(value, dict) and "__children__" in value:
            out.append((name, True, 0, "Mon, 04 Aug 2026 12:00:00 GMT"))
        else:
            assert isinstance(value, bytes)
            out.append((name, False, len(value), "Mon, 04 Aug 2026 12:00:00 GMT"))
    return out


def _make_propfind_response(path: str) -> bytes:
    resources = _listdir(path)
    base = f"/{path.strip('/')}" if path.strip("/") else ""
    parts = ["""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">"""]
    # 加上自己（collection）
    parts.append(f"""  <D:response>
    <D:href>{base if base else '/'}</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype><D:collection/></D:resourcetype>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>""")
    for name, is_dir, size, lm in resources:
        href = f"{base}/{name}" if base else f"/{name}"
        rt = "<D:collection/>" if is_dir else ""
        parts.append(f"""  <D:response>
    <D:href>{href}</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype>{rt}</D:resourcetype>
        <D:getcontentlength>{size}</D:getcontentlength>
        <D:getlastmodified>{lm}</D:getlastmodified>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>""")
    parts.append("</D:multistatus>")
    return "\n".join(parts).encode("utf-8")


class MockDavHandler(BaseHTTPRequestHandler):
    """最小 WebDAV：PROPFIND / MKCOL / PUT / GET / DELETE。"""

    def log_message(self, *args, **kwargs):  # 静音
        pass

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if _accept_anon and not _auth_credentials:
            return True
        if not auth.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return False
        return _auth_credentials.get(username) == password

    def _send_status(self, code, message="", body=b"", content_type="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_PROPFIND(self):
        if not self._check_auth():
            self._send_status(401)
            return
        path = urllib.parse.urlsplit(self.path).path
        body = _make_propfind_response(path)
        self._send_status(207, body=body, content_type="application/xml; charset=utf-8")

    def do_MKCOL(self):
        if not self._check_auth():
            self._send_status(401)
            return
        path = urllib.parse.urlsplit(self.path).path
        parts = path.strip("/").split("/")
        cur = _storage
        for p in parts:
            if p not in cur:
                cur[p] = {"__children__": {}}
            if isinstance(cur[p], bytes):
                self._send_status(405)  # 已存在且是文件
                return
            cur = cur[p]["__children__"]
        self._send_status(201)

    def do_PUT(self):
        if not self._check_auth():
            self._send_status(401)
            return
        path = urllib.parse.urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length) if length else b""
        # 自动建父目录
        parts = path.strip("/").split("/")
        cur = _storage
        for p in parts[:-1]:
            if p not in cur:
                cur[p] = {"__children__": {}}
            cur = cur[p]["__children__"]
        cur[parts[-1]] = data
        self._send_status(201)

    def do_GET(self):
        if not self._check_auth():
            self._send_status(401)
            return
        path = urllib.parse.urlsplit(self.path).path
        cur = _get_storage_path(path)
        if cur is None or isinstance(cur, dict):
            self._send_status(404)
            return
        self._send_status(200, body=cur, content_type="application/octet-stream")

    def do_DELETE(self):
        if not self._check_auth():
            self._send_status(401)
            return
        path = urllib.parse.urlsplit(self.path).path
        parts = path.strip("/").split("/")
        cur = _storage
        for p in parts[:-1]:
            if p not in cur or isinstance(cur[p], bytes):
                self._send_status(404)
                return
            cur = cur[p]["__children__"]
        if parts[-1] in cur:
            del cur[parts[-1]]
            self._send_status(204)
        else:
            self._send_status(404)


def _start_server() -> tuple[ThreadingHTTPServer, str, int]:
    """起 mock WebDAV，返回 (server, host, port)。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockDavHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "127.0.0.1", port


# ── 通用 ASGI 调用 ────────────────────────────────────────────────

async def _raw_request(app, method, path, payload=None, headers=None,
                      query_string: str = ""):
    from urllib.parse import urlsplit
    raw_body = b"" if payload is None else json.dumps(payload).encode()
    sent = []
    body_chunks = []
    status = {"code": 0, "headers": []}

    async def receive():
        if not sent:
            sent.append(True)
            return {"type": "http.request", "body": raw_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
            status["headers"] = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            body_chunks.append(message.get("body", b""))

    full_path = path if not query_string else f"{path}?{query_string}"
    scope = {
        "type": "http", "method": method, "path": urlsplit(full_path).path,
        "query_string": (urlsplit(full_path).query or "").encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("testserver", 80), "client": ("testclient", 50000),
    }
    await app(scope, receive, send)
    return status["code"], b"".join(body_chunks)


# ── App 启动 ──────────────────────────────────────────────────────

def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


# ── 准备 data_root 样例 ──────────────────────────────────────────

def _seed_data(root: Path):
    (root / "songs.json").write_text(
        json.dumps({
            "version": 4,
            "songs": [
                {"id": "local-1", "title": "本地歌 A", "artist": "测试"},
                {"id": "local-2", "title": "本地歌 B", "artist": "测试"},
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "settings.json").write_text(
        json.dumps({
            "output_dir": str(root / "output"),
            "default_canvas": "抖音全屏 9:20",
            "default_theme": "海洋柔光",
            "font_path": str(root / "font.ttf"),
            "backup_count": 20, "render_threads": 1,
            "appearanceMode": "system", "applicationAccentId": "bambooMoon",
        }, ensure_ascii=False),
        encoding="utf-8",
    )


# ── 测试主体 ──────────────────────────────────────────────────────

class M22WebDavApiTests(unittest.TestCase):
    """每条用例启动 mock WebDAV + 独立 app 生命周期。"""

    def setUp(self):
        _reset_storage()
        self.server, self.host, self.port = _start_server()
        self.base_url = f"http://{self.host}:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        _reset_storage()

    def _run(self, coro):
        return asyncio.run(coro)

    def _with_app(self, scenario_coro):
        async def wrapper():
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _seed_data(root)
                app = _boot_app(root)
                async with app.router.lifespan_context(app):
                    return await scenario_coro(app, root)
        return asyncio.run(wrapper())

    # ── 1. 未配置状态下读 config ──

    async def _scenario_get_config_unconfigured(self, app, root):
        code, body = await _raw_request(app, "GET", "/api/backup/webdav/config")
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["configured"], False)

    def test_get_config_unconfigured(self):
        self._with_app(self._scenario_get_config_unconfigured)

    # ── 2. 保存配置 → 重新读（needs_unlock）→ 解锁 ──

    async def _scenario_save_then_get(self, app, root):
        # PUT
        code, body = await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url + "/streamer",
                "username": "alice", "password": "pwd",
                "remote_dir": "/backups",
                "master_password": "master123",
            },
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["ok"], True)
        self.assertIn("updated_at", data)

        # GET 无主密码 → configured but needs_unlock
        code, body = await _raw_request(app, "GET", "/api/backup/webdav/config")
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["configured"], True)
        self.assertEqual(data["needs_unlock"], True)
        # 敏感字段脱敏
        self.assertEqual(data["url"], "")

        # GET 带主密码 → 解锁成功
        qs = urllib.parse.urlencode({"master_password": "master123"})
        code, body = await _raw_request(
            app, "GET", "/api/backup/webdav/config",
            query_string=qs,
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["needs_unlock"], False)
        self.assertEqual(data["url"], self.base_url + "/streamer")
        self.assertEqual(data["username"], "alice")
        self.assertEqual(data["remote_dir"], "/backups")

    def test_save_then_get(self):
        self._with_app(self._scenario_save_then_get)

    # ── 3. 错主密码 GET ──

    async def _scenario_wrong_master_password(self, app, root):
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/", "master_password": "master",
            },
        )
        qs = urllib.parse.urlencode({"master_password": "wrong"})
        code, body = await _raw_request(
            app, "GET", "/api/backup/webdav/config",
            query_string=qs,
        )
        self.assertEqual(code, 400, body)

    def test_wrong_master_password(self):
        self._with_app(self._scenario_wrong_master_password)

    # ── 4. test-saved（已存配置测试连接）──

    async def _scenario_test_saved(self, app, root):
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/backups", "master_password": "master",
            },
        )
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/test-saved",
            payload={"master_password": "master"},
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["ok"], True)
        self.assertEqual(data["status"], 207)

    def test_test_saved(self):
        self._with_app(self._scenario_test_saved)

    # ── 5. test 临时凭证（不写盘） ──

    async def _scenario_test_creds(self, app, root):
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/test",
            payload={"url": self.base_url, "username": "", "password": ""},
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["ok"], True)

    def test_test_creds(self):
        self._with_app(self._scenario_test_creds)

    async def _scenario_test_creds_unreachable(self, app, root):
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/test",
            payload={"url": "http://127.0.0.1:1/never", "username": "", "password": ""},
        )
        # 网络错误应在 service 层捕获并返回 {ok: False}
        data = json.loads(body)
        self.assertEqual(data["ok"], False)
        self.assertIn("网络", data["message"])

    def test_test_creds_unreachable(self):
        self._with_app(self._scenario_test_creds_unreachable)

    # ── 6. push 完整流程（mock 远端 + 验证 PUT）──

    async def _scenario_push(self, app, root):
        # 先存配置
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/backups", "master_password": "master",
            },
        )
        # push
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/push",
            payload={"master_password": "master"},
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["ok"], True)
        self.assertTrue(data["remote_name"].startswith("push-"))
        self.assertTrue(data["remote_name"].endswith(".songworkbench"))
        self.assertGreater(data["file_count"], 0)
        # 远端存储确实有文件
        self.assertTrue(len(_storage) > 0, "mock 远端应收到文件")

    def test_push(self):
        self._with_app(self._scenario_push)

    # ── 7. list_remote ──

    async def _scenario_list(self, app, root):
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/backups", "master_password": "master",
            },
        )
        # 先 push 一个
        await _raw_request(
            app, "POST", "/api/backup/webdav/push",
            payload={"master_password": "master"},
        )
        # list
        code, body = await _raw_request(
            app, "GET", "/api/backup/webdav/list",
            query_string=urllib.parse.urlencode({"master_password": "master"}),
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertGreaterEqual(len(data["files"]), 1)
        for f in data["files"]:
            self.assertTrue(f["name"].endswith(".songworkbench"))

    def test_list(self):
        self._with_app(self._scenario_list)

    # ── 8. pull 完整流程（先 push 再 pull 到另一个 data_root）──

    async def _scenario_pull(self, app, root):
        # 在 mock 远端预置一个 .songworkbench
        import zipfile, io, hashlib
        from tools.backup import export_backup
        # 临时建个 "远端" data
        remote_src = root / "remote_src"
        remote_src.mkdir()
        (remote_src / "songs.json").write_text(
            json.dumps({
                "version": 4,
                "songs": [{"id": "remote-x", "title": "从云端拉回的歌"}],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        (remote_src / "settings.json").write_text(
            json.dumps({
                "output_dir": str(remote_src / "output"),
                "default_canvas": "抖音全屏 9:20",
                "default_theme": "海洋柔光",
                "font_path": str(remote_src / "font.ttf"),
                "backup_count": 20, "render_threads": 1,
                "appearanceMode": "system", "applicationAccentId": "bambooMoon",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        # 内存生成 .songworkbench
        tmp = root / "tmp.songworkbench"
        export_backup(output=tmp, data_root=remote_src, password=None)
        # 推到 mock 远端（直接走 urllib 简化）
        req = urllib.request.Request(
            f"{self.base_url}/backups/from-cloud.songworkbench",
            data=tmp.read_bytes(),
            method="PUT",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertIn(resp.status, (200, 201, 204))
        tmp.unlink()

        # 在本地 data_root 配 WebDAV
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/backups", "master_password": "master",
            },
        )
        # pull
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/pull",
            payload={"master_password": "master", "remote_name": "from-cloud.songworkbench"},
        )
        self.assertEqual(code, 200, body)
        data = json.loads(body)
        self.assertEqual(data["ok"], True)
        # 本地 songs.json 已被覆盖
        songs = json.loads((root / "songs.json").read_text(encoding="utf-8"))
        titles = [s["title"] for s in songs["songs"]]
        self.assertIn("从云端拉回的歌", titles)

    def test_pull(self):
        self._with_app(self._scenario_pull)

    # ── 9. 错主密码 push ──

    async def _scenario_push_wrong_master(self, app, root):
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/x", "master_password": "master",
            },
        )
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/push",
            payload={"master_password": "wrong"},
        )
        self.assertEqual(code, 400, body)

    def test_push_wrong_master(self):
        self._with_app(self._scenario_push_wrong_master)

    # ── 10. 未配置调用 push ──

    async def _scenario_push_unconfigured(self, app, root):
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/push",
            payload={"master_password": "any"},
        )
        self.assertEqual(code, 400, body)

    def test_push_unconfigured(self):
        self._with_app(self._scenario_push_unconfigured)

    # ── 11. 鉴权失败（mock 远端要求密码但客户端传错）──

    async def _scenario_auth_failed(self, app, root):
        # 启用 mock 鉴权：账号 alice / 密码 secret
        global _accept_anon
        _accept_anon = False
        _auth_credentials["alice"] = "secret"

        # 测试连接：客户端传错密码
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/test",
            payload={"url": self.base_url, "username": "alice", "password": "wrong"},
        )
        data = json.loads(body)
        self.assertEqual(data["ok"], False)
        # service test_connection 返回 {ok: False, status: 401, message: ...}
        self.assertEqual(data["status"], 401)

    def test_auth_failed(self):
        self._with_app(self._scenario_auth_failed)

    # ── 12. clear 配置 ──

    async def _scenario_clear(self, app, root):
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/x", "master_password": "master",
            },
        )
        # clear
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/config/clear",
            payload={"master_password": "master"},
        )
        self.assertEqual(code, 200, body)
        # 再读 → 未配置
        code, body = await _raw_request(app, "GET", "/api/backup/webdav/config")
        data = json.loads(body)
        self.assertEqual(data["configured"], False)

    def test_clear(self):
        self._with_app(self._scenario_clear)

    # ── 13. save 校验（缺字段）──

    async def _scenario_save_validation(self, app, root):
        # URL 不合法
        code, body = await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": "ftp://x", "username": "u", "password": "p",
                "remote_dir": "/x", "master_password": "master",
            },
        )
        self.assertEqual(code, 400, body)
        # remote_dir 空
        code, body = await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "", "master_password": "master",
            },
        )
        self.assertEqual(code, 400, body)

    def test_save_validation(self):
        self._with_app(self._scenario_save_validation)

    # ── 14. pull 缺 remote_name ──

    async def _scenario_pull_no_name(self, app, root):
        await _raw_request(
            app, "PUT", "/api/backup/webdav/config",
            payload={
                "url": self.base_url, "username": "u", "password": "p",
                "remote_dir": "/x", "master_password": "master",
            },
        )
        code, body = await _raw_request(
            app, "POST", "/api/backup/webdav/pull",
            payload={"master_password": "master"},
        )
        self.assertEqual(code, 400, body)

    def test_pull_no_name(self):
        self._with_app(self._scenario_pull_no_name)


if __name__ == "__main__":
    unittest.main()
