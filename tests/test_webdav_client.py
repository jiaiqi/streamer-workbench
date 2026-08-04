"""M2.2 WebDAV 客户端单测（不依赖外部服务）。

覆盖：
- URL 拼接与基本校验
- PROPFIND 响应解析
- 状态码 → 错误类型映射
- 鉴权头注入
- path traversal 防御（_is_safe_backup_name 由 service 测试覆盖）
"""
from __future__ import annotations

import base64
import urllib.error
from email.message import Message
from unittest.mock import patch, MagicMock

import pytest

from core.webdav import (
    WebDavClient,
    WebDavError,
    WebDavAuthError,
    WebDavNetworkError,
    WebDavNotFoundError,
    WebDavProtocolError,
    _join_url,
    _parse_propfind_response,
)


# ── URL 拼接 ──────────────────────────────────────────────────────

class TestJoinUrl:
    def test_no_trailing_slash(self):
        assert _join_url("https://dav.example.com/streamer", "/backups") == \
            "https://dav.example.com/streamer/backups"
        assert _join_url("https://dav.example.com/streamer/", "/backups") == \
            "https://dav.example.com/streamer/backups"

    def test_relative_path_normalized(self):
        assert _join_url("https://dav.example.com/streamer", "backups/file") == \
            "https://dav.example.com/streamer/backups/file"

    def test_empty_path(self):
        assert _join_url("https://dav.example.com/streamer", "") == \
            "https://dav.example.com/streamer"

    def test_root_path(self):
        # "/" 经 rstrip 后为空，再加回 "/"；HTTP 请求末尾 / 无副作用
        assert _join_url("https://dav.example.com", "/") == \
            "https://dav.example.com/"


# ── 构造与基本校验 ────────────────────────────────────────────────

class TestWebDavClientInit:
    def test_basic(self):
        client = WebDavClient("https://dav.example.com/streamer", "user", "pwd")
        assert client._base_url == "https://dav.example.com/streamer"

    def test_trailing_slash_normalized(self):
        client = WebDavClient("https://dav.example.com/streamer/", "user", "pwd")
        assert client._base_url == "https://dav.example.com/streamer"

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="http/https"):
            WebDavClient("ftp://dav.example.com", "u", "p")

    def test_no_host(self):
        with pytest.raises(ValueError, match="host"):
            WebDavClient("https:///path", "u", "p")

    def test_empty_credentials_allowed(self):
        client = WebDavClient("https://dav.example.com", "", "")
        assert client._username == ""


# ── PROPFIND 响应解析 ──────────────────────────────────────────────

class TestParsePropfindResponse:
    BASE = "https://dav.example.com/streamer"

    def test_collection(self):
        body = b"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/streamer/backups/</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype><D:collection/></D:resourcetype>
        <D:getcontentlength>0</D:getcontentlength>
        <D:getlastmodified>Mon, 04 Aug 2026 12:00:00 GMT</D:getlastmodified>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""
        result = _parse_propfind_response(body, base_href=self.BASE)
        assert len(result) == 1
        r = result[0]
        assert r.is_collection is True
        assert r.size == 0
        assert "Mon, 04 Aug 2026" in r.last_modified

    def test_file(self):
        body = b"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/streamer/backups/push-20260804.songworkbench</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype/>
        <D:getcontentlength>12345</D:getcontentlength>
        <D:getlastmodified>Mon, 04 Aug 2026 12:00:00 GMT</D:getlastmodified>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""
        result = _parse_propfind_response(body, base_href=self.BASE)
        assert len(result) == 1
        r = result[0]
        assert r.is_collection is False
        assert r.size == 12345

    def test_multiple_responses(self):
        body = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/streamer/backups/</D:href>
    <D:propstat>
      <D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/streamer/backups/a.songworkbench</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype/>
        <D:getcontentlength>100</D:getcontentlength>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""
        result = _parse_propfind_response(body, base_href=self.BASE)
        assert len(result) == 2
        assert result[0].is_collection is True
        assert result[1].is_collection is False

    def test_malformed_xml(self):
        with pytest.raises(WebDavProtocolError, match="XML"):
            _parse_propfind_response(b"<broken", base_href=self.BASE)

    def test_missing_href_skipped(self):
        body = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:propstat>
      <D:prop><D:resourcetype/></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/streamer/backups/ok</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype><D:collection/></D:resourcetype>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""
        result = _parse_propfind_response(body, base_href=self.BASE)
        # 无 href 的 response 跳过
        assert len(result) == 1
        assert result[0].href == "/streamer/backups/ok"

    def test_404_propstat_skipped(self):
        # propstat 状态码非 200（如 404 not found）跳过该 prop
        body = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/streamer/missing/</D:href>
    <D:propstat>
      <D:prop><D:resourcetype/></D:prop>
      <D:status>HTTP/1.1 404 Not Found</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""
        result = _parse_propfind_response(body, base_href=self.BASE)
        # 资源在但 propstat 404 → size=0, is_collection=False（默认值）
        assert len(result) == 1
        assert result[0].is_collection is False
        assert result[0].size == 0


# ── 请求层：状态码映射 + 鉴权头注入 ───────────────────────────────

class _MockResponse:
    """模拟 urllib 返回的 Response。"""
    def __init__(self, status, body=b"", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or Message()
        # 给 headers 加 get_content-length 等基础字段
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(body))

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestListDir:
    def test_207_success(self):
        body = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/streamer/backups/file.zip</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype/>
        <D:getcontentlength>100</D:getcontentlength>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(207, body)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            result = client.listdir("/backups")
            assert len(result) == 1
            assert result[0].href == "/streamer/backups/file.zip"

    def test_404_raises_not_found(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(404)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavNotFoundError):
                client.listdir("/missing")

    def test_401_raises_auth(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(401)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavAuthError):
                client.listdir("/")

    def test_500_raises_protocol(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(500)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavProtocolError):
                client.listdir("/")

    def test_network_error(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.side_effect = urllib.error.URLError("dns fail")
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavNetworkError):
                client.listdir("/")


class TestEnsureCollection:
    def test_201_created(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(201)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            client.ensure_collection("/backups")  # 不抛

    def test_405_already_exists(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(405)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            client.ensure_collection("/backups")  # 不抛（已存在）

    def test_401_raises_auth(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(401)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavAuthError):
                client.ensure_collection("/backups")


class TestUpload:
    def test_201_put(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(201)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            client.upload("/backups/test.zip", b"abc")  # 不抛

    def test_401_raises_auth(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(401)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavAuthError):
                client.upload("/backups/test.zip", b"abc")

    def test_409_raises_protocol(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(409)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavProtocolError):
                client.upload("/backups/test.zip", b"abc")


class TestDownload:
    def test_200(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(200, b"hello")
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            assert client.download("/backups/test.zip") == b"hello"

    def test_404_raises_not_found(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(404)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            with pytest.raises(WebDavNotFoundError):
                client.download("/backups/missing.zip")


class TestDelete:
    def test_204(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(204)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            client.delete("/backups/test.zip")

    def test_404_idempotent(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(404)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            client.delete("/backups/missing.zip")  # 不抛


class TestTestConnection:
    def test_207_ok(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(207, b'<?xml version="1.0"?><D:multistatus xmlns:D="DAV:"></D:multistatus>')
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            result = client.test_connection()
            assert result["ok"] is True
            assert result["status"] == 207

    def test_401_auth_fail(self):
        with patch.object(WebDavClient, "_build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.return_value = _MockResponse(401)
            mock_opener.return_value = opener_inst
            client = WebDavClient("https://dav.example.com/streamer", "u", "p")
            result = client.test_connection()
            assert result["ok"] is False
            assert "账号或密码" in result["message"]


class TestAuthHeader:
    """验证 Basic Auth 头被正确注入。"""

    def test_basic_auth_header(self):
        captured = {}

        class CaptureHandler(urllib.request.BaseHandler):
            def http_request(self, req):
                captured["auth"] = req.get_header("Authorization")
                return req
            https_request = http_request

        from urllib.request import build_opener
        opener = build_opener(CaptureHandler())
        client = WebDavClient("https://dav.example.com/streamer", "alice", "secret")
        # 直接验证 _build_opener 返回的 opener 含 AuthHandler
        test_opener = client._build_opener()
        # 抓取 _AuthHandler 实例
        for handler in test_opener.handlers:
            if handler.__class__.__name__ == "_AuthHandler":
                # 触发一次 fake request 验证 auth header
                req = urllib.request.Request("https://dav.example.com/x", method="PROPFIND")
                handler.http_request(req)
                expected = "Basic " + base64.b64encode(b"alice:secret").decode("ascii")
                assert req.get_header("Authorization") == expected
                return
        pytest.fail("_AuthHandler 未在 opener 中找到")

    def test_anonymous_no_header(self):
        client = WebDavClient("https://dav.example.com/streamer", "", "")
        # 不抛错 + opener 中无 _AuthHandler
        opener = client._build_opener()
        for handler in opener.handlers:
            assert handler.__class__.__name__ != "_AuthHandler"
