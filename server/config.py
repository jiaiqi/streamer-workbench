"""应用启动配置与路径解析。

本模块不创建目录、不加载业务数据，可在测试和 CLI 参数解析阶段安全导入。
"""
from __future__ import annotations

import json
import ipaddress
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import urlsplit


AppMode = Literal["development", "desktop", "test"]
DATA_DIR_ENV = "STREAMER_WORKBENCH_DATA_DIR"
ALLOWED_ORIGINS_ENV = "STREAMER_WORKBENCH_ALLOWED_ORIGINS"
SESSION_TOKEN_ENV = "STREAMER_WORKBENCH_SESSION_TOKEN"

# development 模式: 默认白名单覆盖所有 loopback 端口 (any-port wildcard)。
#   - 安全边界: R0.10 的第一道防线是 host loopback 检查 (is_loopback_host),
#     dev 模式来源都是 loopback, Origin 检查只是"防 cross-tab 误改"的 UX 保护。
#   - 实际原因: Vite/CRA/Next 等 dev server 端口可被项目配置 (--port 5174 等),
#     钉死 5173 拖慢 dev 体验。production 模式不进入此分支, 仍要求显式白名单。
DEFAULT_DEVELOPMENT_ORIGINS = (
    "http://localhost",
    "http://127.0.0.1",
)


def is_loopback_host(host: str) -> bool:
    candidate = host.strip().strip("[]")
    if candidate.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _validate_origin(origin: str) -> str:
    origin = origin.strip().rstrip("/")
    if not origin or origin == "*":
        raise ValueError("CORS 来源必须是明确地址，不能使用通配符")
    parsed = urlsplit(origin)
    if parsed.scheme in ("http", "https"):
        if (not parsed.hostname or not is_loopback_host(parsed.hostname)
                or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError(f"CORS 来源必须是 loopback origin：{origin}")
    elif parsed.scheme == "app":
        if (parsed.netloc != "streamer-workbench"
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError(f"无效的桌面应用 origin：{origin}")
    else:
        raise ValueError(f"不支持的 CORS origin scheme：{origin}")
    return origin


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
    session_token: str | None = None

    def __post_init__(self):
        if self.mode not in ("development", "desktop", "test"):
            raise ValueError(f"未知应用模式：{self.mode}")
        project_root = _absolute(Path(self.project_root))
        object.__setattr__(self, "project_root", project_root)
        if not is_loopback_host(self.host):
            raise ValueError(f"本地服务只允许监听 loopback 地址：{self.host}")
        object.__setattr__(self, "host", self.host.strip().strip("[]"))
        if self.mode == "test" and self.data_root is None:
            raise ValueError("test 模式必须显式提供临时 data_root")
        if self.data_root is not None:
            object.__setattr__(self, "data_root", _absolute(Path(self.data_root)))
        if self.startup_config_path is not None:
            object.__setattr__(self, "startup_config_path",
                               _absolute(Path(self.startup_config_path)))
        origins = tuple(dict.fromkeys(
            _validate_origin(origin) for origin in self.allowed_origins
        ))
        object.__setattr__(self, "allowed_origins", origins)
        token = (self.session_token or "").strip() or None
        object.__setattr__(self, "session_token", token)

    @classmethod
    def from_environment(cls, *, mode: AppMode = "development",
                         environ: Mapping[str, str] | None = None) -> "AppConfig":
        root = Path(__file__).resolve().parent.parent
        environ = environ if environ is not None else os.environ
        raw_origins = str(environ.get(ALLOWED_ORIGINS_ENV) or "").strip()
        origins = (
            tuple(origin.strip() for origin in raw_origins.split(",")
                  if origin.strip())
            if raw_origins
            else (DEFAULT_DEVELOPMENT_ORIGINS if mode == "development" else ())
        )
        return cls(
            project_root=root,
            mode=mode,
            allowed_origins=origins,
            session_token=str(environ.get(SESSION_TOKEN_ENV) or "").strip() or None,
        )


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
    posters_dir: Path
    live_sessions_dir: Path
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


DataRootSource = Literal[
    "explicit", "environment", "startup", "development", "platform",
]


def resolve_data_root_source(
    config: AppConfig, *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> tuple[Path, Path, DataRootSource]:
    """解析数据目录并报告来源；优先级与 resolve_data_root 完全一致。"""
    environ = environ if environ is not None else os.environ
    startup_path = config.startup_config_path or platform_startup_config(
        platform, environ, home)
    if config.data_root is not None:
        return config.data_root, startup_path, "explicit"
    env_value = str(environ.get(DATA_DIR_ENV) or "").strip()
    if env_value:
        return _absolute(Path(env_value)), startup_path, "environment"
    from_startup = _startup_data_root(startup_path)
    if from_startup is not None:
        return from_startup, startup_path, "startup"
    if config.mode == "development":
        return config.project_root / "data", startup_path, "development"
    return platform_data_root(platform, environ, home), startup_path, "platform"


def resolve_data_root(config: AppConfig, *,
                      environ: Mapping[str, str] | None = None,
                      platform: str | None = None,
                      home: Path | None = None) -> tuple[Path, Path]:
    """按显式配置、环境、启动配置、开发目录、平台默认值依次解析。"""
    data_root, startup_path, _source = resolve_data_root_source(
        config, environ=environ, platform=platform, home=home)
    return data_root, startup_path


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
        posters_dir=data_root / "posters",
        live_sessions_dir=data_root / "live-sessions",
        layouts_dir=data_root / "layouts",
        backups_dir=data_root / "backups",
        output_dir=data_root / "output",
        startup_config_path=startup_path,
    )
