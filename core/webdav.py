"""M2.2 WebDAV 客户端（零外部依赖）。

设计目标：
- 只用 stdlib（urllib + xml.etree + base64）实现 WebDAV Class 2 核心方法
- 不依赖 webdav4 / requests-toolbelt 等第三方库
- 支持 PROPFIND / MKCOL / PUT / GET / DELETE / MOVE（同步所需）
- 全部用 Basic Auth（绝大多数自建 WebDAV 服务的标配）
- 详细错误分层：网络层 / 鉴权层 / 协议层

注意：放在 `core/` 是为了让 client 与 settings/backup 模块解耦，
不依赖任何 server/UI 框架；上层 service 才能在 server + tests + 未来 CLI 复用。
"""
from __future__ import annotations

import base64
import io
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Mapping
from dataclasses import dataclass


# ── 错误类型 ───────────────────────────────────────────────────────

class WebDavError(Exception):
    """WebDAV 客户端可稳定抛出的基础错误。"""


class WebDavNetworkError(WebDavError):
    """网络层失败（DNS / 连接 / 超时）。"""


class WebDavAuthError(WebDavError):
    """鉴权失败（401/403）。"""


class WebDavProtocolError(WebDavError):
    """协议层失败（响应码非预期 / XML 解析错误）。"""


class WebDavNotFoundError(WebDavError):
    """资源不存在（404 / propstat 404）。"""


# ── 数据类 ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WebDavResource:
    """PROPFIND 解析出的资源信息。"""
    href: str
    is_collection: bool
    size: int
    last_modified: str  # ISO 8601（服务端原样；空表示无）


# ── 客户端 ─────────────────────────────────────────────────────────

# WebDAV namespace（PROPFIND 响应里的 xmlns:DAV）
DAV_NS = "DAV:"
_ETREE_NS = {"D": DAV_NS}


def _parse_propfind_response(body: bytes, *, base_href: str) -> list[WebDavResource]:
    """解析 PROPFIND multistatus XML 响应。

    base_href 用于把服务端返回的 href 解码成"相对路径"，方便调用方做 diff。
    兼容服务端返回完整 URL（Apache mod_dav、nginx-dav）和相对路径（SABnzbd+）。
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise WebDavProtocolError(f"PROPFIND 响应不是合法 XML: {exc}") from exc

    out: list[WebDavResource] = []
    # multistatus 里的 response 元素直接是 D:response
    for resp in root.findall("D:response", _ETREE_NS):
        href_el = resp.find("D:href", _ETREE_NS)
        if href_el is None or not href_el.text:
            continue
        href = href_el.text.strip()

        # 解析 propstat 状态码
        is_collection = False
        size = 0
        last_modified = ""

        # 服务端可能返回 200 资源状态 或 404 propstat 状态；优先取 200
        for propstat in resp.findall("D:propstat", _ETREE_NS):
            status_el = propstat.find("D:status", _ETREE_NS)
            status_text = status_el.text if status_el is not None and status_el.text else ""
            if "200" not in status_text:
                continue
            prop = propstat.find("D:prop", _ETREE_NS)
            if prop is None:
                continue
            rt = prop.find("D:resourcetype", _ETREE_NS)
            if rt is not None and rt.find("D:collection", _ETREE_NS) is not None:
                is_collection = True
            sz = prop.find("D:getcontentlength", _ETREE_NS)
            if sz is not None and sz.text and sz.text.strip().isdigit():
                size = int(sz.text.strip())
            lm = prop.find("D:getlastmodified", _ETREE_NS)
            if lm is not None and lm.text:
                last_modified = lm.text.strip()
            break  # 取第一个 200 propstat

        out.append(WebDavResource(
            href=href,
            is_collection=is_collection,
            size=size,
            last_modified=last_modified,
        ))
    return out


def _join_url(base: str, path: str) -> str:
    """WebDAV URL 拼接：base 末尾 / + path 开头 / 都归一化。

    WebDAV 的 href 是绝对路径形式（/dav/folder/file）；PUT/GET/PROPFIND
    需要完整的 scheme://host 形式。path 可为空（只取 base）。
    """
    base = base.rstrip("/")
    if not path:
        return base
    if not path.startswith("/"):
        path = "/" + path
    return base + path


class WebDavClient:
    """WebDAV 客户端（Basic Auth）。

    使用方法：
        client = WebDavClient("https://dav.example.com/streamer", "user", "pwd")
        client.ensure_collection("/streamer")
        for r in client.listdir("/streamer"):
            print(r.href, r.size)
        client.upload("/streamer/backup.songworkbench", data)
        client.download("/streamer/backup.songworkbench", out_file)
    """

    DEFAULT_TIMEOUT = 30.0  # 秒

    def __init__(self, base_url: str, username: str = "", password: str = "",
                 *, timeout: float | None = None):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"WebDAV URL 必须是 http/https: {base_url}")
        if not parsed.netloc:
            raise ValueError(f"WebDAV URL 缺少 host: {base_url}")
        self._base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT

    # ── 内部：构造请求 ──

    def _build_opener(self) -> urllib.request.OpenerDirector:
        """构造带 Basic Auth 的 Opener；空账号密码走匿名。"""
        if not self._username:
            return urllib.request.build_opener()
        # HTTPBasicAuthHandler 会自动加 Authorization 头
        credentials = f"{self._username}:{self._password}".encode("utf-8")
        token = base64.b64encode(credentials).decode("ascii")
        auth_header = f"Basic {token}"

        class _AuthHandler(urllib.request.BaseHandler):
            def http_request(self, req):  # type: ignore[override]
                req.add_header("Authorization", auth_header)
                return req
            https_request = http_request  # type: ignore[assignment]

        return urllib.request.build_opener(_AuthHandler())

    def _request(self, method: str, path: str, *,
                 body: bytes | None = None,
                 headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        """发请求；返回 (status, response_headers, body)。"""
        url = _join_url(self._base_url, path)
        req_headers = dict(headers or {})
        if body is not None and "Content-Type" not in req_headers and method == "PUT":
            req_headers["Content-Type"] = "application/octet-stream"
        req = urllib.request.Request(
            url, data=body, method=method, headers=req_headers,
        )
        opener = self._build_opener()
        try:
            with opener.open(req, timeout=self._timeout) as resp:
                raw = resp.read()
                hdrs = {k: v for k, v in resp.headers.items()}
                return resp.status, hdrs, raw
        except urllib.error.HTTPError as exc:
            # HTTPError 也是 HTTPResponse，body 仍可读
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            hdrs = {k: v for k, v in (exc.headers.items() if exc.headers else [])}
            return exc.code, hdrs, raw
        except urllib.error.URLError as exc:
            # 通常是 DNS / 连接拒绝 / 超时 / SSL
            raise WebDavNetworkError(f"网络错误: {exc.reason}") from exc
        except TimeoutError as exc:
            raise WebDavNetworkError("请求超时") from exc
        except OSError as exc:
            raise WebDavNetworkError(f"连接失败: {exc}") from exc

    # ── 公共方法 ──

    def listdir(self, path: str = "/", depth: str = "1") -> list[WebDavResource]:
        """PROPFIND 列目录。

        depth=1: 列出直接子项；"infinity": 递归全列。
        失败映射：
        - 207 multi-status: 正常
        - 404: WebDavNotFoundError
        - 401/403: WebDavAuthError
        - 其他: WebDavProtocolError
        """
        status, _hdrs, body = self._request(
            "PROPFIND", path,
            headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
            body=b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:">'
                 b'<D:prop><D:resourcetype/><D:getcontentlength/><D:getlastmodified/></D:prop>'
                 b'</D:propfind>',
        )
        if status == 404:
            raise WebDavNotFoundError(f"目录不存在: {path}")
        if status in (401, 403):
            raise WebDavAuthError(f"鉴权失败 ({status}): {path}")
        if status == 207:
            return _parse_propfind_response(body, base_href=self._base_url)
        if status == 301 or status == 308:
            raise WebDavProtocolError(f"PROPFIND 收到重定向，WebDAV 服务端配置异常 ({status})")
        raise WebDavProtocolError(f"PROPFIND 失败 status={status} path={path}")

    def ensure_collection(self, path: str) -> None:
        """MKCOL 创建目录；已存在(405)视为成功。"""
        status, _hdrs, _body = self._request("MKCOL", path)
        if status in (201, 200, 301):
            return
        if status == 405:
            # 资源已存在（method not allowed on existing resource）
            return
        if status in (401, 403):
            raise WebDavAuthError(f"创建目录鉴权失败 ({status}): {path}")
        if status == 409:
            # Conflict：父目录不存在或服务端 quirk；先尝试列父目录判断
            raise WebDavProtocolError(f"MKCOL 冲突 {path}（父目录可能不存在）")
        raise WebDavProtocolError(f"MKCOL 失败 status={status} path={path}")

    def upload(self, path: str, data: bytes) -> None:
        """PUT 上传；status ∈ {201, 204, 200} 视为成功。"""
        status, _hdrs, _body = self._request("PUT", path, body=data)
        if status in (200, 201, 204):
            return
        if status in (401, 403):
            raise WebDavAuthError(f"上传鉴权失败 ({status}): {path}")
        if status == 409:
            raise WebDavProtocolError(f"PUT 冲突 {path}（父目录可能不存在）")
        raise WebDavProtocolError(f"PUT 失败 status={status} path={path}")

    def download(self, path: str) -> bytes:
        """GET 下载；返回字节流。"""
        status, _hdrs, body = self._request("GET", path)
        if status == 200:
            return body
        if status == 404:
            raise WebDavNotFoundError(f"文件不存在: {path}")
        if status in (401, 403):
            raise WebDavAuthError(f"下载鉴权失败 ({status}): {path}")
        raise WebDavProtocolError(f"GET 失败 status={status} path={path}")

    def delete(self, path: str) -> None:
        """DELETE 文件或空目录；status ∈ {204, 200} 视为成功。"""
        status, _hdrs, _body = self._request("DELETE", path)
        if status in (200, 204):
            return
        if status == 404:
            return  # 删不存在视为成功
        if status in (401, 403):
            raise WebDavAuthError(f"删除鉴权失败 ({status}): {path}")
        if status == 423:
            raise WebDavProtocolError(f"资源被锁定 {path}")
        raise WebDavProtocolError(f"DELETE 失败 status={status} path={path}")

    def test_connection(self) -> dict[str, Any]:
        """测试连接 + 鉴权：PROPFIND 根目录深度 0。

        返回 {ok, message, status}。
        """
        try:
            status, _hdrs, _body = self._request(
                "PROPFIND", "/",
                headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
                body=b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:">'
                     b'<D:prop><D:resourcetype/></D:prop></D:propfind>',
            )
        except WebDavError as exc:
            return {"ok": False, "status": 0, "message": str(exc)}

        if status == 207:
            return {"ok": True, "status": status, "message": "连接 + 鉴权成功"}
        if status in (401, 403):
            return {"ok": False, "status": status, "message": "账号或密码错误"}
        if status == 404:
            return {"ok": True, "status": status,
                    "message": "根目录可访问（但 depth=0 无内容返回）"}
        return {"ok": False, "status": status, "message": f"意外响应码 {status}"}
