"""M2.7 在线元数据层错误类型。

错误分类：
- MetadataNotFound：请求合法但查不到（用户搜的关键词没结果）
- MetadataUnavailable：所有 provider 都失败（网络/限流/5xx）
- MetadataRateLimited：被限流（429），UI 可提示「稍后重试」
- MetadataError：基类（catch all）
"""
from __future__ import annotations


class MetadataError(Exception):
    """metadata 层基础异常。UI 层可统一 catch 此基类。"""
    pass


class MetadataNotFound(MetadataError):
    """provider 全部都查不到（合法请求，无结果）。

    不是错误，是"没数据"。UI 应当显示"未找到"而非"网络错误"。
    """
    pass


class MetadataUnavailable(MetadataError):
    """所有 provider 失败（网络/限流/5xx）。

    errors 是 [(provider_name, exception), ...] 列表，UI 可展示
    "网易云: timeout, QQ: 403, 酷狗: 5xx" 这样的明细。
    """
    def __init__(self, errors: list[tuple[str, Exception]]):
        self.errors = list(errors)
        if not self.errors:
            detail = "no providers configured"
        else:
            detail = ", ".join(
                f"{name}: {type(exc).__name__}: {exc}"
                for name, exc in self.errors
            )
        super().__init__(f"所有 provider 都不可用：{detail}")


class MetadataRateLimited(MetadataError):
    """被限流（HTTP 429）。

    retry_after 单位是秒（来自 Retry-After header）；None 表示服务端没说。
    """
    def __init__(self, provider: str, retry_after: int | None = None):
        self.provider = provider
        self.retry_after = retry_after
        msg = f"{provider} 被限流"
        if retry_after is not None:
            msg += f"，请 {retry_after} 秒后重试"
        super().__init__(msg)
