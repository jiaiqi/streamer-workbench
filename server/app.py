"""FastAPI 应用工厂。构造阶段不写盘，运行时资源由 lifespan 管理。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.engine import render_page
from server.api.handlers import install_api_contract
from server.config import AppConfig, build_app_paths
from server.context import AppContext
from server.dependencies import get_app_context
from server.ports.repositories import BackupPolicy, RepositoryRecoveryRequired
from server.repositories.events import FileEventStore
from server.repositories.presets import FilePresetRepository
from server.repositories.settings import FileSettingsRepository
from server.repositories.songs import FileSongRepository
from server.services.export import ExportApplicationService
from server.services.songs import SongApplicationService
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
            # 启动时完成 Schema 校验，损坏数据阻止 context 发布。
            song_repository.load()
            settings_repository.load()
            preset_repository.recover()
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
                render_service=render_page,
                song_service=song_service,
                tab_service=tab_service,
                export_service=export_service,
                export_job_manager=app.state.export_jobs, themes=app.state.themes,
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
    paths = build_app_paths(config)
    app = FastAPI(title="主播工作台 · 渲染后端",
                  lifespan=_lifespan(config, paths))
    app.state.config = config
    app.state.paths = paths
    install_api_contract(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins) or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # `check_dir=False` 允许全新 data_root 在 lifespan 中初始化。
    app.mount("/bg", StaticFiles(directory=str(paths.themes_dir), check_dir=False),
              name="theme_bg")
    app.mount("/tabs", StaticFiles(directory=str(paths.tabs_dir), check_dir=False),
              name="song_tabs")

    from server.routers import songs, render, export, events, settings, presets
    app.include_router(songs.router)
    app.include_router(render.router)
    app.include_router(export.router)
    app.include_router(events.router)
    app.include_router(settings.router)
    app.include_router(presets.router)

    @app.get("/api/health")
    def health(request: Request):
        context = get_app_context(request)
        library = context.song_repository.load().value
        return {"ok": True, "themes": len(context.themes),
                "songs": len(library.mastered())}

    return app
