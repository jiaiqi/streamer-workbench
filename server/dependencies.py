"""FastAPI request dependencies。"""
from fastapi import Request

from server.context import AppContext


def get_app_context(request: Request) -> AppContext:
    """返回当前请求所属 app 的唯一 AppContext。"""
    context = getattr(request.app.state, "context", None)
    if context is None:
        raise RuntimeError("应用尚未完成 lifespan 初始化")
    return context
