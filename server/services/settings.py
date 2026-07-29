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
        return settings
