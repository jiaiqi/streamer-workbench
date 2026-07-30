"""FastAPI 应用工厂。构造阶段不写盘，运行时资源由 lifespan 管理。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.engine import render_page
from core.data.live import RequestPolicy
from server.api.handlers import (
    REQUEST_ID_HEADER,
    SESSION_TOKEN_HEADER,
    install_api_contract,
)
from server.config import AppConfig, build_app_paths
from server.context import AppContext
from server.dependencies import get_app_context
from server.ports.repositories import BackupPolicy, RepositoryRecoveryRequired
from server.repositories.events import FileEventStore
from server.repositories.live import FileLiveRepository
from server.repositories.posters import FilePosterRepository
from server.repositories.presets import FilePresetRepository
from server.repositories.settings import FileSettingsRepository
from server.repositories.songs import FileSongRepository
from server.services.data_dir import DataDirectoryService
from server.services.export import ExportApplicationService
from server.services.live_persistence import LiveSessionPersistenceService
from server.services.posters import PosterApplicationService
from server.services.presets import PresetApplicationService
from server.services.request_policy import RequestPolicyService
from server.services.songs import SongApplicationService
from server.services.settings import SettingsApplicationService
from server.services.tabs import TabApplicationService

logger = logging.getLogger("streamer-workbench")


def _lifespan(config: AppConfig, paths):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # R0.6 第一切片沿用 deps 作为临时适配器；初始化被严格延后到 lifespan。
        from server.deps import default_settings, initialize_legacy_state

        initialize_legacy_state(app, paths)
        resources = []
        try:
            song_repository = FileSongRepository(
                paths.songs_json, BackupPolicy(paths.backups_dir / "songs"))
            resources.append(song_repository)
            settings_repository = FileSettingsRepository(
                paths.settings_json, BackupPolicy(paths.backups_dir / "settings"),
                defaults=default_settings(paths))
            resources.append(settings_repository)
            event_store = FileEventStore(paths.events_jsonl)
            resources.append(event_store)
            preset_repository = FilePresetRepository(
                paths.presets_dir, BackupPolicy(paths.backups_dir / "presets"))
            resources.append(preset_repository)
            poster_repository = FilePosterRepository(
                paths.posters_dir, BackupPolicy(paths.backups_dir / "posters"))
            resources.append(poster_repository)
            live_repository = FileLiveRepository(
                paths.live_sessions_dir,
                BackupPolicy(paths.backups_dir / "live-sessions"))
            resources.append(live_repository)
            # 启动时完成 Schema 校验，损坏数据阻止 context 发布。
            song_repository.load()
            settings_repository.load()
            preset_repository.recover()
            poster_repository.recover()
            live_repository.recover()
            if preset_repository.get("_default") is None:
                from core.data.presets import Preset
                preset_repository.save(Preset.default(), expected_revision=None)
            export_service = ExportApplicationService(
                song_repository=song_repository,
                settings_repository=settings_repository,
                event_store=event_store,
                export_job_manager=app.state.export_jobs,
                themes=app.state.themes,
                font_path=paths.fonts_dir / "MaokenAssortedSans.ttf",
            )
            song_service = SongApplicationService(
                song_repository=song_repository,
                event_store=event_store,
            )
            preset_service = PresetApplicationService(
                preset_repository=preset_repository,
            )
            poster_service = PosterApplicationService(
                poster_repository=poster_repository,
                song_repository=song_repository,
            )
            # R2 P3 直播持久化桥: 启动期自动 load 所有已存 session
            live_persistence_service = LiveSessionPersistenceService(
                live_repository=live_repository,
                policy_factory=lambda rv: RequestPolicyService(
                    policy=RequestPolicy(rule_version=rv)),
                event_store=event_store,
            )
            for sid in live_persistence_service.list_sessions():
                try:
                    live_persistence_service.load_session(sid)
                except RepositoryUnavailable:
                    logger.exception("live session 恢复失败: %s", sid)
            settings_service = SettingsApplicationService(
                settings_repository=settings_repository,
            )
            data_dir_service = DataDirectoryService(config=config, paths=paths)
            tab_service = TabApplicationService(
                song_repository=song_repository,
                event_store=event_store,
                tabs_root=paths.tabs_dir,
                transactions_root=paths.backups_dir / "tab-transactions",
            )
            tab_recovery = tab_service.recover()
            if tab_recovery.unresolved:
                raise RepositoryRecoveryRequired(
                    "曲谱附件事务存在无法自动恢复的状态："
                    + ", ".join(tab_recovery.unresolved))
            context = AppContext(
                config=config, paths=paths,
                song_repository=song_repository, event_store=event_store,
                preset_repository=preset_repository,
                settings_repository=settings_repository,
                poster_repository=poster_repository,
                live_persistence_service=live_persistence_service,
                render_service=render_page,
                song_service=song_service,
                preset_service=preset_service,
                settings_service=settings_service,
                data_dir_service=data_dir_service,
                tab_service=tab_service,
                export_service=export_service,
                export_job_manager=app.state.export_jobs, themes=app.state.themes,
                poster_service=poster_service,
            )
            app.state.context = context
            try:
                yield
            finally:
                app.state.export_jobs.close()
                del app.state.context
        finally:
            for resource in reversed(resources):
                try:
                    resource.close()
                except Exception:
                    logger.exception("关闭 Repository 资源失败")

    return lifespan


def create_app(config: AppConfig | None = None) -> FastAPI:
    """创建尚未启动的 app；不得在此创建用户目录或加载业务数据。"""
    config = config or AppConfig.from_environment(mode="development")
    if config.mode == "desktop":
        if not config.session_token:
            raise ValueError("desktop 模式必须配置每次启动生成的会话令牌")
        if len(config.session_token) < 32:
            raise ValueError("desktop 模式会话令牌至少需要 32 个字符")
    paths = build_app_paths(config)
    app = FastAPI(title="主播工作台 · 渲染后端",
                  lifespan=_lifespan(config, paths))
    app.state.config = config
    app.state.paths = paths
    install_api_contract(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER, SESSION_TOKEN_HEADER],
    )

    # `check_dir=False` 允许全新 data_root 在 lifespan 中初始化。
    app.mount("/bg", StaticFiles(directory=str(paths.themes_dir), check_dir=False),
              name="theme_bg")
    app.mount("/tabs", StaticFiles(directory=str(paths.tabs_dir), check_dir=False),
              name="song_tabs")

    from server.routers import songs, render, export, events, settings, presets, posters
    from server.routers import live
    app.include_router(songs.router)
    app.include_router(render.router)
    app.include_router(export.router)
    app.include_router(events.router)
    app.include_router(settings.router)
    app.include_router(presets.router)
    app.include_router(posters.router)
    app.include_router(live.router)

    @app.get("/api/health")
    def health(request: Request):
        context = get_app_context(request)
        library = context.song_repository.load().value
        return {"ok": True, "themes": len(context.themes),
                "songs": len(library.mastered())}

    return app
