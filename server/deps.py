"""服务依赖（deps）：替换模块级全局变量，通过 FastAPI app.state 注入。

使用方式（router 中）：
    from server.deps import get_themes, get_library
    themes = get_themes(request.app.state)

初始化（main.py）：
    from server.deps import init_deps
    init_deps(app)
"""
import os
import json
import logging
from functools import lru_cache

from core.spec import CANVAS_PRESETS
from core.themes.loader import load_themes
from core.layouts import get_layout
from core.data.songs import SongLibrary, build_default_library
from core.data.events import EVENT_TYPES, append_event, iter_events, tail as events_tail
from core.data import tabs as tabs_store
from core.data.presets import init_presets
from core.engine import render_page

logger = logging.getLogger("streamer-workbench")


# ── 路径常量（由 init_deps 根据 ROOT 计算）──
ROOT: str = ""
THEMES_DIR: str = ""
FONT: str = ""
SONGS_JSON: str = ""
SETTINGS_PATH: str = ""
EVENTS_JSONL: str = ""
TABS_DIR: str = ""
DATA_ROOT: str = ""


# ── 默认设置 ──
DEFAULT_SETTINGS = {
    "output_dir": "",
    "default_canvas": "抖音全屏 9:20",
    "default_theme": "海洋柔光",
    "font_path": "",
    "backup_count": 20,
    "render_threads": 1,
}


def _load_settings() -> dict:
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception as e:
            logger.warning("settings.json 读取失败，使用默认值：%s", e)
    return DEFAULT_SETTINGS.copy()


def _save_settings(s: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def init_deps(app, root: str = None, data_root: str = None):
    """初始化所有服务依赖，挂载到 app.state。在 main.py 启动时调用一次。"""
    global ROOT, THEMES_DIR, FONT, SONGS_JSON, SETTINGS_PATH, EVENTS_JSONL, TABS_DIR, DATA_ROOT

    ROOT = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    THEMES_DIR = os.path.join(ROOT, "themes")
    FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")
    DATA_ROOT = data_root or os.path.join(ROOT, "data")
    SONGS_JSON = os.path.join(DATA_ROOT, "songs.json")
    SETTINGS_PATH = os.path.join(DATA_ROOT, "settings.json")
    EVENTS_JSONL = os.path.join(DATA_ROOT, "events.jsonl")
    TABS_DIR = os.path.join(DATA_ROOT, "tabs")
    os.makedirs(TABS_DIR, exist_ok=True)

    # 设置默认输出目录
    DEFAULT_SETTINGS["output_dir"] = os.path.join(DATA_ROOT, "output")
    DEFAULT_SETTINGS["font_path"] = FONT

    # 加载主题、歌曲库、设置
    app.state.themes = load_themes(THEMES_DIR)
    app.state.library = build_default_library(json_path=SONGS_JSON)
    app.state.settings = _load_settings()

    # 批量导出任务
    app.state.export_jobs = {}

    # 缩略图缓存
    app.state.thumb_cache = {}

    # 初始化预设目录
    init_presets(DATA_ROOT)

    logger.info("deps 初始化完成，主题: %d 首，歌曲: %d 首",
                len(app.state.themes), len(app.state.library.mastered()))


# ── 便捷访问器（router 中调用）──

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
    for s in library.mastered():
        n = len(s.title)
        key = str(n) if n <= 6 else "7+"
        out[key] = out.get(key, 0) + 1
    return out
