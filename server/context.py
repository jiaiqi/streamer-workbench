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
    poster_repository: Any
    render_service: Any
    song_service: Any
    preset_service: Any
    settings_service: Any
    data_dir_service: Any
    tab_service: Any
    export_service: Any
    export_job_manager: Any
    poster_service: Any                  # R1a.1 增量
    themes: Mapping[str, Any]
    live_persistence_service: Any = None  # R2 P3 增量
    practice_service: Any = None        # P4 R2 增量
    discovery_service: Any = None       # R3 学歌发现增量
    stats_service: Any = None           # R4 统计聚合增量
    metadata_router: Any = None         # M2.7+ 在线元数据 Router（multi-provider）
