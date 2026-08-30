"""设置用例服务：统一默认值、校验、兼容回退与 Repository CAS。"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


APPEARANCE_MODES = frozenset({"system", "light", "dark"})
APPLICATION_ACCENT_IDS = frozenset({
    "bambooMoon",
    "rainSky",
    "distantMountain",
    "rouge",
    "begonia",
    "wisteria",
    "amber",
    "pineFlower",
})
DEFAULT_APPEARANCE_MODE = "system"
DEFAULT_APPLICATION_ACCENT_ID = "bambooMoon"

# M2.4 WebDAV 自动同步字段
AUTO_SYNC_DIRECTIONS = frozenset({"push", "pull", "both"})
DEFAULT_AUTO_SYNC_DIRECTION = "push"
DEFAULT_AUTO_SYNC_INTERVAL_MINUTES = 60
MIN_AUTO_SYNC_INTERVAL_MINUTES = 1
MAX_AUTO_SYNC_INTERVAL_MINUTES = 1440  # 24 小时


class SettingsServiceError(Exception):
    """设置用例的稳定业务错误基类。"""


class SettingsValidationFailed(SettingsServiceError):
    """设置值不满足应用层约束。"""


class SettingsApplicationService:
    """对外提供设置快照和局部更新；持久化仍由 Repository 负责。"""

    def __init__(self, *, settings_repository):
        self._repository = settings_repository

    def get(self) -> dict[str, Any]:
        return self._normalize(self._repository.load().value)

    def update(self, changes: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(changes, Mapping):
            raise SettingsValidationFailed("设置更新必须是对象")
        snapshot = self._repository.load()
        settings = copy.deepcopy(snapshot.value)
        settings.update(copy.deepcopy(dict(changes)))
        normalized = self._normalize(settings)
        saved = self._repository.save(
            normalized, expected_revision=snapshot.revision)
        return self._normalize(saved.value)

    @staticmethod
    def _normalize(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SettingsValidationFailed("设置文档必须是对象")
        settings = copy.deepcopy(dict(value))

        for key in ("output_dir", "default_canvas", "default_theme", "font_path"):
            if not isinstance(settings.get(key), str):
                raise SettingsValidationFailed(f"{key} 必须是字符串")
        backup_count = settings.get("backup_count")
        if (not isinstance(backup_count, int) or isinstance(backup_count, bool)
                or not 0 <= backup_count <= 100):
            raise SettingsValidationFailed("backup_count 必须是 0–100 的整数")
        render_threads = settings.get("render_threads")
        if (not isinstance(render_threads, int) or isinstance(render_threads, bool)
                or not 1 <= render_threads <= 16):
            raise SettingsValidationFailed("render_threads 必须是 1–16 的整数")

        if settings.get("appearanceMode") not in APPEARANCE_MODES:
            settings["appearanceMode"] = DEFAULT_APPEARANCE_MODE
        if settings.get("applicationAccentId") not in APPLICATION_ACCENT_IDS:
            settings["applicationAccentId"] = DEFAULT_APPLICATION_ACCENT_ID

        # M2.4 自动同步：宽松校验，错误兜底默认
        enabled = settings.get("webdav_auto_sync_enabled")
        if enabled is None:
            settings["webdav_auto_sync_enabled"] = False
        elif not isinstance(enabled, bool):
            raise SettingsValidationFailed("webdav_auto_sync_enabled 必须是 bool")
        interval = settings.get("webdav_auto_sync_interval_minutes")
        if interval is None:
            settings["webdav_auto_sync_interval_minutes"] = DEFAULT_AUTO_SYNC_INTERVAL_MINUTES
        elif (not isinstance(interval, int) or isinstance(interval, bool)
              or not MIN_AUTO_SYNC_INTERVAL_MINUTES <= interval <= MAX_AUTO_SYNC_INTERVAL_MINUTES):
            raise SettingsValidationFailed(
                f"webdav_auto_sync_interval_minutes 必须是 "
                f"{MIN_AUTO_SYNC_INTERVAL_MINUTES}-{MAX_AUTO_SYNC_INTERVAL_MINUTES} 的整数"
            )
        direction = settings.get("webdav_auto_sync_direction")
        if direction is None:
            settings["webdav_auto_sync_direction"] = DEFAULT_AUTO_SYNC_DIRECTION
        elif direction not in AUTO_SYNC_DIRECTIONS:
            raise SettingsValidationFailed(
                f"webdav_auto_sync_direction 必须是 {sorted(AUTO_SYNC_DIRECTIONS)} 之一"
            )
        # last_* 状态字段：nullable 字符串
        for key in ("webdav_auto_sync_last_at", "webdav_auto_sync_last_status",
                    "webdav_auto_sync_last_error", "webdav_auto_sync_last_remote_name"):
            v = settings.get(key)
            if v is not None and not isinstance(v, str):
                raise SettingsValidationFailed(f"{key} 必须是字符串或 null")

        # P0-1（2026-08-30 8/18 评估 6.5）：
        # 旧字段 webdav_auto_sync_master_password_b64 不再使用；主密码已迁到密钥环。
        # 这里静默擦除，不再报错（旧 settings.json 残留自动清理）。
        if "webdav_auto_sync_master_password_b64" in settings:
            settings.pop("webdav_auto_sync_master_password_b64", None)
        return settings
