"""M2.7 HttpClient（基于 stdlib urllib.request）。

为什么不用 requests/httpx：
- 零新增依赖（requirements.txt 只有 fastapi/uvicorn/pillow/pypinyin/pyzipper）
- M2.7 是基础层，避免引入第三方 HTTP 库
- 异步/连接池等高级特性 M2.7 不需要

特性：
- 默认 User-Agent（避免被 403）
- 超时（默认 10s）
- 指数退避重试（最多 2 次，仅 5xx/网络错误；4xx 不重试）
- 429 单独处理：抛 MetadataRateLimited，带 retry_after
- 同 provider 串行 + ≥ min_interval 间隔（简单可靠的速率限制）
- JSON 解析失败抛 MetadataUnavailable（业务层统一处理）
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import MetadataRateLimited, MetadataUnavailable


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class HttpClient:
    """薄 HTTP 客户端封装（基于 stdlib urllib.request）。"""

    def __init__(
        self,
        *,
        user_agent: str = _DEFAULT_UA,
        timeout: float = 10.0,
        max_retries: int = 2,
        min_interval: float = 0.2,
        retry_backoff: float = 0.5,
        sleep: Any = None,
    ):
        """构造 HttpClient。

        Args:
            user_agent: HTTP UA；某些 API 不带 UA 会 403
            timeout: 单次请求超时（秒）
            max_retries: 5xx/网络错误的最大重试次数（不含首次）
            min_interval: 同 client 的最小调用间隔（秒）
            retry_backoff: 退避基数（实际等待 = backoff * 2^attempt）
            sleep: 注入的 sleep 函数（用于测试）；默认 time.sleep
        """
        self._ua = user_agent
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._retry_backoff = retry_backoff
        self._sleep = sleep if sleep is not None else time.sleep
        self._lock = threading.Lock()
        self._last_call_at: float = 0.0

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        """GET → 解析 JSON。

        Raises:
            MetadataUnavailable: 网络/超时/5xx/解析失败
            MetadataRateLimited: 429（带 retry_after）
        """
        text = self.get_text(url, params=params)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise MetadataUnavailable(
                [("self", exc)]
            ) from exc

    def get_text(self, url: str, *, params: dict | None = None) -> str:
        """GET → 文本。

        完整的"等待 + 重试 + 速率限制"逻辑集中在这里。
        """
        full_url = self._build_url(url, params)
        last_exc: Exception | None = None
        # 速率限制：调用前先 sleep 到满足 min_interval
        with self._lock:
            self._throttle()
            # 实际重试也要在锁内做（避免重试间隔被并发请求打乱）
            for attempt in range(self._max_retries + 1):
                try:
                    return self._do_request(full_url)
                except urllib.error.HTTPError as exc:
                    if exc.code == 429:
                        # 限流不重试，直接抛（让 router 跳下一个 provider）
                        retry_after = self._parse_retry_after(exc)
                        raise MetadataRateLimited(
                            "http", retry_after
                        ) from exc
                    if 400 <= exc.code < 500:
                        # 4xx 是客户端错误，重试无意义
                        raise MetadataUnavailable(
                            [("http", exc)]
                        ) from exc
                    # 5xx 才重试
                    last_exc = exc
                except (urllib.error.URLError, OSError) as exc:
                    # 网络/超时，重试
                    last_exc = exc
                if attempt < self._max_retries:
                    self._sleep(self._retry_backoff * (2 ** attempt))
        # 重试耗尽
        raise MetadataUnavailable([("http", last_exc)])

    # ── 内部辅助 ──

    def _throttle(self) -> None:
        """在锁内调用：保证两次调用之间至少 min_interval 秒。"""
        if self._last_call_at <= 0:
            self._last_call_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < self._min_interval:
            self._sleep(self._min_interval - elapsed)
        self._last_call_at = time.monotonic()

    def _do_request(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": self._ua})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    @staticmethod
    def _build_url(url: str, params: dict | None) -> str:
        if not params:
            return url
        qs = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{qs}"

    @staticmethod
    def _parse_retry_after(exc: urllib.error.HTTPError) -> int | None:
        """从 429 响应头解析 Retry-After。"""
        ra = exc.headers.get("Retry-After") if exc.headers else None
        if ra is None:
            return None
        try:
            return int(ra)
        except (TypeError, ValueError):
            return None
