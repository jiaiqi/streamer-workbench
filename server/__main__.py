"""受控本地开发服务器入口：只允许使用 AppConfig 校验后的 loopback 地址。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn

from server.config import AppConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动主播工作台本地后端")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    return parser


def _launch_options(config: AppConfig, *, port: int, reload: bool) -> dict:
    if not 1 <= port <= 65535:
        raise ValueError(f"端口超出有效范围：{port}")
    return {
        "host": config.host,
        "port": port,
        "reload": reload,
    }


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    config = AppConfig.from_environment(mode="development")
    uvicorn.run(
        "server.main:app",
        **_launch_options(config, port=args.port, reload=args.reload),
    )


if __name__ == "__main__":
    main()
