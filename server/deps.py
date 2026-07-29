"""R0.6 临时数据适配器；所有输入均来自当前 app 的 AppPaths。"""
import json
import logging
import os

from core.data.presets import init_presets
from core.data.songs import SongLibrary, build_default_library
from core.themes.loader import load_themes

logger = logging.getLogger("streamer-workbench")

DEFAULT_SETTINGS = {
    "output_dir": "",
    "default_canvas": "抖音全屏 9:20",
    "default_theme": "海洋柔光",
    "font_path": "",
    "backup_count": 20,
    "render_threads": 1,
}


def load_settings(path, *, output_dir, font_path) -> dict:
    defaults = {**DEFAULT_SETTINGS, "output_dir": str(output_dir),
                "font_path": str(font_path)}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                return {**defaults, **json.load(stream)}
        except Exception as error:
            logger.warning("settings.json 读取失败，使用默认值：%s", error)
    return defaults


def save_settings(path, settings: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(settings, stream, ensure_ascii=False, indent=2)


def initialize_legacy_state(app, paths):
    """lifespan 内构造当前 app 私有的临时状态，无模块路径绑定。"""
    os.makedirs(paths.tabs_dir, exist_ok=True)
    app.state.themes = load_themes(str(paths.themes_dir))
    app.state.library = build_default_library(json_path=str(paths.songs_json))
    app.state.settings = load_settings(
        str(paths.settings_json), output_dir=paths.output_dir,
        font_path=paths.fonts_dir / "MaokenAssortedSans.ttf")
    app.state.export_jobs = {}
    app.state.thumb_cache = {}
    app.state.presets_dir = init_presets(str(paths.data_root))


def get_themes(state) -> dict:
    return state.themes


def get_library(state) -> SongLibrary:
    return state.library


def get_settings(state) -> dict:
    return state.settings


def get_export_jobs(state) -> dict:
    return state.export_jobs


def get_thumb_cache(state) -> dict:
    return state.thumb_cache


def _count_by_len(library):
    out = {}
    for song in library.mastered():
        size = len(song.title)
        key = str(size) if size <= 6 else "7+"
        out[key] = out.get(key, 0) + 1
    return out
