"""FastAPI 应用工厂。构造阶段不写盘，运行时资源由 lifespan 管理。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.engine import render_page
from server.config import AppConfig, build_app_paths
from server.context import AppContext
from server.dependencies import get_app_context

logger = logging.getLogger("streamer-workbench")


def _lifespan(config: AppConfig, paths):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # R0.6 第一切片沿用 deps 作为临时适配器；初始化被严格延后到 lifespan。
        from server.deps import initialize_legacy_state

        initialize_legacy_state(app, paths)
        context = AppContext(
            config=config,
            paths=paths,
            song_repository=app.state.library,
            event_store=paths.events_jsonl,
            preset_repository=app.state.presets_dir,
            settings_repository=app.state.settings,
            render_service=render_page,
            export_job_manager=app.state.export_jobs,
            themes=app.state.themes,
        )
        app.state.context = context
        try:
            yield
        finally:
            app.state.export_jobs.clear()
            del app.state.context

    return lifespan


def create_app(config: AppConfig | None = None) -> FastAPI:
    """创建尚未启动的 app；不得在此创建用户目录或加载业务数据。"""
    config = config or AppConfig.from_environment(mode="development")
    paths = build_app_paths(config)
    app = FastAPI(title="主播工作台 · 渲染后端",
                  lifespan=_lifespan(config, paths))
    app.state.config = config
    app.state.paths = paths

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
        library = context.song_repository
        return {"ok": True, "themes": len(context.themes),
                "songs": len(library.mastered())}

    return app
