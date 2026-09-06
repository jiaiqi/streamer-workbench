"""FastAPI 应用工厂。构造阶段不写盘，运行时资源由 lifespan 管理。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.engine import render_page
from core.data.live import RequestPolicy
from core.outbox import LocalOutbox
from server.api.handlers import (
    REQUEST_ID_HEADER,
    SESSION_TOKEN_HEADER,
    install_api_contract,
)
from server.config import AppConfig, build_app_paths
from server.context import AppContext
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
            # P0-2b: outbox（与 events.jsonl 配套；启动时 drain 把未发事件补到 events）
            outbox = LocalOutbox(paths.outbox_jsonl)
            resources.append(outbox)
            # 启动 drain — 把上次崩溃或失败留下的 outbox 事件 push 到 events
            drain_report = outbox.drain(event_store.append)
            if drain_report["drained"] > 0:
                logger.info(
                    "outbox drain 启动补发 %d 条事件到 events.jsonl",
                    drain_report["drained"])
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
                outbox=outbox,  # P0-2c: CRUD 事件先入 outbox，state 落盘后 drain
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
                outbox=outbox,  # P0-2c: 事件先入 outbox，state 落盘后 drain
            )
            for sid in live_persistence_service.list_sessions():
                try:
                    live_persistence_service.load_session(sid)
                except RepositoryUnavailable:
                    logger.exception("live session 恢复失败: %s", sid)
            # P4 R2: PracticeApplicationService 打卡 + 统计
            from server.services.practice import PracticeApplicationService
            practice_service = PracticeApplicationService(
                event_store=event_store, song_repository=song_repository,
            )
            # R3: DiscoveryApplicationService 学歌发现 (3 套机制 + 智能推荐)
            from server.services.discovery import DiscoveryApplicationService
            discovery_service = DiscoveryApplicationService(
                event_store=event_store, song_repository=song_repository,
            )
            # R4: StatsApplicationService 统计聚合
            # 海报已导出数: 扫 posters 目录
            poster_count = 0
            try:
                if paths.posters_dir.is_dir():
                    poster_count = sum(1 for _ in paths.posters_dir.rglob("*.json"))
            except Exception:
                poster_count = 0
            from server.services.stats import StatsApplicationService
            stats_service = StatsApplicationService(
                event_store=event_store,
                song_repository=song_repository,
                poster_count=poster_count,
            )
            settings_service = SettingsApplicationService(
                settings_repository=settings_repository,
            )
            # M2.7+/M2.8 在线元数据服务：构造 Router + Cache
            # 默认只接 NeteaseProvider；M2.10+ 扩展 QQ / Kugou
            from server.services.metadata import (
                MetadataApplicationService,
                build_default_router,
            )
            metadata_router, metadata_cache = build_default_router(
                paths.metadata_dir,
            )
            metadata_service = MetadataApplicationService(
                metadata_router, cache=metadata_cache,
            )
            data_dir_service = DataDirectoryService(config=config, paths=paths)
            # M2.2 WebDAV 同步服务
            from server.services.webdav_sync import WebDavSyncService
            webdav_service = WebDavSyncService(
                settings_service=settings_service,
                data_root=paths.data_root,
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
                poster_repository=poster_repository,
                live_persistence_service=live_persistence_service,
                practice_service=practice_service,
                discovery_service=discovery_service,
                stats_service=stats_service,
                render_service=render_page,
                song_service=song_service,
                preset_service=preset_service,
                settings_service=settings_service,
                data_dir_service=data_dir_service,
                tab_service=tab_service,
                export_service=export_service,
                export_job_manager=app.state.export_jobs, themes=app.state.themes,
                poster_service=poster_service,
                metadata_router=metadata_router,  # M2.7+/M2.8
                webdav_service=webdav_service,    # M2.2
            )
            # M2.4 自动同步调度器
            from server.services.auto_sync import AutoSyncScheduler
            auto_sync_scheduler = AutoSyncScheduler(
                webdav_service=webdav_service,
                settings_service=settings_service,
            )
            context.auto_sync_scheduler = auto_sync_scheduler
            # 启动后台循环（如果 enabled）— 等 stop 时 await 完成
            await auto_sync_scheduler.start()
            app.state.context = context
            try:
                yield
            finally:
                # M2.4 停止自动同步后台循环（await 确保 task 完整结束）
                try:
                    await auto_sync_scheduler.stop()
                except Exception:
                    logger.exception("停止 AutoSyncScheduler 失败")
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
    from server.routers import live, practice, discovery, stats, learning_report
    from server.routers import exports, audio
    app.include_router(songs.router)
    app.include_router(render.router)
    app.include_router(export.router)
    app.include_router(events.router)
    app.include_router(settings.router)
    app.include_router(presets.router)
    app.include_router(posters.router)
    app.include_router(live.router)
    app.include_router(practice.router)
    app.include_router(discovery.router)
    app.include_router(stats.router)
    app.include_router(learning_report.router)
    app.include_router(exports.router)
    app.include_router(audio.router)
    from server.routers import metadata  # M2.7+/M2.8 在线元数据
    app.include_router(metadata.router)
    # R4 Runtime v2 v2.5: Theme × Layout 能力矩阵
    from server.routers import compatibility
    app.include_router(compatibility.router)
    from server.routers import webdav  # M2.2 WebDAV 同步
    app.include_router(webdav.router)
    from server.routers import auto_sync as auto_sync_router  # M2.4 自动同步
    app.include_router(auto_sync_router.router)
    from server.routers import health  # P0-4b: 本地后端健康检查
    app.include_router(health.router)

    return app
