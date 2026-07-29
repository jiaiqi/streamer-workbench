"""单个 FastAPI 应用实例的显式运行时上下文。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from server.config import AppConfig, AppPaths


@dataclass
class AppContext:
    """R0.6 依赖容器；R0.7 将临时适配器替换为 Repository 实现。"""

    config: AppConfig
    paths: AppPaths
    song_repository: Any
    event_store: Any
    preset_repository: Any
    settings_repository: Any
    render_service: Any
    song_service: Any
    preset_service: Any
    tab_service: Any
    export_service: Any
    export_job_manager: Any
    themes: Mapping[str, Any]
