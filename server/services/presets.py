"""Preset 应用服务：统一场景预设业务规则与 Repository CAS。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.data.presets import (
    CURRENT_SCHEMA_VERSION,
    Preset,
    _from_dict,
    new_preset_id,
    validate_song_query,
)
from server.ports.repositories import MISSING_REVISION


class PresetServiceError(Exception):
    """可由 HTTP 适配层稳定映射的预设业务错误。"""


class PresetValidationFailed(PresetServiceError):
    pass


class PresetNotFound(PresetServiceError):
    pass


class PresetProtected(PresetServiceError):
    pass


@dataclass(frozen=True)
class PresetSaveResult:
    preset: Preset
    revision: str


@dataclass(frozen=True)
class PresetDuplicateResult:
    preset: Preset
    revision: str


@dataclass(frozen=True)
class PresetDefaultResult:
    preset_id: str
    summaries: tuple[Any, ...]
    revision: str


class PresetApplicationService:
    """将 Preset 业务规则从 Router 下沉到可测试应用边界。"""

    def __init__(self, *, preset_repository):
        self._presets = preset_repository

    def list(self):
        return self._presets.list().value

    def get(self, preset_id: str) -> Preset:
        snapshot = self._presets.get(preset_id)
        if snapshot is None:
            raise PresetNotFound(f"预设不存在：{preset_id}")
        return snapshot.value

    def save(self, payload: Mapping[str, Any]) -> PresetSaveResult:
        try:
            preset = _from_dict(dict(payload))
        except (TypeError, ValueError, AttributeError) as error:
            raise PresetValidationFailed(f"预设字段不合法：{error}") from error
        if not preset.id:
            preset.id = new_preset_id()
        if preset.schema_version != CURRENT_SCHEMA_VERSION:
            raise PresetValidationFailed(
                f"Preset 必须使用 Schema v{CURRENT_SCHEMA_VERSION}")
        preset.name = str(preset.name or "").strip()
        if not preset.name:
            raise PresetValidationFailed("Preset 名称不能为空")
        current = self._presets.get(preset.id)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        if current is None:
            preset.created_at = now
            # 兼容保留 `_default` 身份；普通创建请求不得伪造默认状态。
            preset.is_default = preset.id == "_default"
            expected_revision = MISSING_REVISION
        else:
            # 身份、创建时间和默认状态均由服务端持有，完整更新不能重写。
            preset.created_at = current.value.created_at
            preset.is_default = current.value.is_default
            expected_revision = current.revision
        try:
            validate_song_query(preset.song_query)
        except (TypeError, ValueError, AttributeError) as error:
            raise PresetValidationFailed(str(error)) from error
        saved = self._presets.save(
            preset, expected_revision=expected_revision)
        return PresetSaveResult(saved.value, saved.revision)

    def duplicate(
        self, preset_id: str, *, name: str = ""
    ) -> PresetDuplicateResult:
        if self._presets.get(preset_id) is None:
            raise PresetNotFound(f"预设不存在：{preset_id}")
        target = Preset(id=new_preset_id(), name=str(name or "").strip())
        saved = self._presets.duplicate(preset_id, target)
        return PresetDuplicateResult(saved.value, saved.revision)

    def delete(self, preset_id: str) -> None:
        current = self._presets.get(preset_id)
        if current is None:
            raise PresetNotFound(f"预设不存在：{preset_id}")
        if preset_id == "_default" or current.value.is_default:
            raise PresetProtected("当前默认预设不可删除，请先切换默认预设")
        deleted = self._presets.delete(
            preset_id, expected_revision=current.revision)
        if not deleted:
            raise PresetNotFound(f"预设不存在：{preset_id}")

    def set_default(self, preset_id: str) -> PresetDefaultResult:
        if self._presets.get(preset_id) is None:
            raise PresetNotFound(f"预设不存在：{preset_id}")
        listing = self._presets.list()
        saved = self._presets.set_default(
            preset_id, expected_revision=listing.revision)
        return PresetDefaultResult(preset_id, saved.value, saved.revision)
