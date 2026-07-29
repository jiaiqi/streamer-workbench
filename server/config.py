"""应用启动配置与路径解析。

本模块不创建目录、不加载业务数据，可在测试和 CLI 参数解析阶段安全导入。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping


AppMode = Literal["development", "desktop", "test"]
DATA_DIR_ENV = "STREAMER_WORKBENCH_DATA_DIR"


def _absolute(path: Path, *, base: Path | None = None) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        if base is None:
            raise ValueError(f"路径必须是绝对路径：{path}")
        path = base / path
    return path.resolve(strict=False)


def platform_data_root(platform: str | None = None,
                       environ: Mapping[str, str] | None = None,
                       home: Path | None = None) -> Path:
    """返回平台默认用户数据目录；参数可注入以便跨平台测试。"""
    platform = platform or sys.platform
    environ = environ if environ is not None else os.environ
    home = (home or Path.home()).expanduser().resolve(strict=False)
    if platform.startswith("win"):
        appdata = str(environ.get("APPDATA") or "").strip()
        if not appdata:
            raise ValueError("Windows 缺少 APPDATA，无法确定用户数据目录")
        return _absolute(Path(appdata)) / "streamer-workbench"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "streamer-workbench"
    xdg = str(environ.get("XDG_DATA_HOME") or "").strip()
    base = _absolute(Path(xdg)) if xdg else home / ".local" / "share"
    return base / "streamer-workbench"


def platform_startup_config(platform: str | None = None,
                            environ: Mapping[str, str] | None = None,
                            home: Path | None = None) -> Path:
    """启动配置独立于 data_root，避免 settings.json 自我定位。"""
    platform = platform or sys.platform
    environ = environ if environ is not None else os.environ
    home = (home or Path.home()).expanduser().resolve(strict=False)
    if platform.startswith("win"):
        appdata = str(environ.get("APPDATA") or "").strip()
        if not appdata:
            raise ValueError("Windows 缺少 APPDATA，无法确定启动配置目录")
        base = _absolute(Path(appdata))
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        xdg = str(environ.get("XDG_CONFIG_HOME") or "").strip()
        base = _absolute(Path(xdg)) if xdg else home / ".config"
    return base / "streamer-workbench" / "startup.json"


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    mode: AppMode = "development"
    data_root: Path | None = None
    startup_config_path: Path | None = None
    host: str = "127.0.0.1"
    allowed_origins: tuple[str, ...] = ()

    def __post_init__(self):
        if self.mode not in ("development", "desktop", "test"):
            raise ValueError(f"未知应用模式：{self.mode}")
        project_root = _absolute(Path(self.project_root))
        object.__setattr__(self, "project_root", project_root)
        if self.mode == "test" and self.data_root is None:
            raise ValueError("test 模式必须显式提供临时 data_root")
        if self.data_root is not None:
            object.__setattr__(self, "data_root", _absolute(Path(self.data_root)))
        if self.startup_config_path is not None:
            object.__setattr__(self, "startup_config_path",
                               _absolute(Path(self.startup_config_path)))

    @classmethod
    def from_environment(cls, *, mode: AppMode = "development") -> "AppConfig":
        root = Path(__file__).resolve().parent.parent
        return cls(project_root=root, mode=mode)


@dataclass(frozen=True)
class AppPaths:
    project_root: Path
    themes_dir: Path
    palettes_dir: Path
    skins_dir: Path
    fonts_dir: Path
    data_root: Path
    songs_json: Path
    events_jsonl: Path
    settings_json: Path
    tabs_dir: Path
    presets_dir: Path
    layouts_dir: Path
    backups_dir: Path
    output_dir: Path
    startup_config_path: Path


def _startup_data_root(path: Path) -> Path | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    raw = str(payload.get("data_root") or "").strip()
    return _absolute(Path(raw)) if raw else None


def resolve_data_root(config: AppConfig, *,
                      environ: Mapping[str, str] | None = None,
                      platform: str | None = None,
                      home: Path | None = None) -> tuple[Path, Path]:
    """按显式配置、环境、启动配置、开发目录、平台默认值依次解析。"""
    environ = environ if environ is not None else os.environ
    startup_path = config.startup_config_path or platform_startup_config(
        platform, environ, home)
    if config.data_root is not None:
        return config.data_root, startup_path
    env_value = str(environ.get(DATA_DIR_ENV) or "").strip()
    if env_value:
        return _absolute(Path(env_value)), startup_path
    from_startup = _startup_data_root(startup_path)
    if from_startup is not None:
        return from_startup, startup_path
    if config.mode == "development":
        return config.project_root / "data", startup_path
    return platform_data_root(platform, environ, home), startup_path


def build_app_paths(config: AppConfig, *,
                    environ: Mapping[str, str] | None = None,
                    platform: str | None = None,
                    home: Path | None = None) -> AppPaths:
    """纯派生 AppPaths；不创建或修改任何文件。"""
    data_root, startup_path = resolve_data_root(
        config, environ=environ, platform=platform, home=home)
    root = config.project_root
    return AppPaths(
        project_root=root,
        themes_dir=root / "themes",
        palettes_dir=root / "palettes",
        skins_dir=root / "skins",
        fonts_dir=root / "fonts",
        data_root=data_root,
        songs_json=data_root / "songs.json",
        events_jsonl=data_root / "events.jsonl",
        settings_json=data_root / "settings.json",
        tabs_dir=data_root / "tabs",
        presets_dir=data_root / "presets",
        layouts_dir=data_root / "layouts",
        backups_dir=data_root / "backups",
        output_dir=data_root / "output",
        startup_config_path=startup_path,
    )
