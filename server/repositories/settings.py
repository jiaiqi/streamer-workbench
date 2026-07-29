"""SettingsRepository 的 JSON 文件 adapter。"""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from server.ports.repositories import (
    BackupPolicy,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryUnavailable,
    SettingsDocument,
    StoredSnapshot,
)
from server.repositories.atomic_json import AtomicJsonWriter, MISSING_REVISION, json_revision


class FileSettingsRepository:
    """保留未知字段、拒绝 data_root，并以 CAS 防止 lost update。"""

    def __init__(
        self,
        path: Path,
        backup_policy: BackupPolicy,
        *,
        defaults: Mapping[str, Any] | None = None,
        writer: AtomicJsonWriter | None = None,
    ):
        self._path = Path(path).expanduser().resolve()
        self._backup_policy = backup_policy
        self._defaults = copy.deepcopy(dict(defaults or {}))
        self._validate_document(self._defaults)
        self._writer = writer or AtomicJsonWriter()
        self._lock = threading.RLock()
        self._closed = False

    def load(self) -> StoredSnapshot[SettingsDocument]:
        with self._lock:
            self._ensure_open()
            if not self._path.exists():
                return StoredSnapshot(copy.deepcopy(self._defaults), MISSING_REVISION)
            raw = self._read_raw()
            value = {**copy.deepcopy(self._defaults), **copy.deepcopy(raw)}
            self._validate_document(value)
            return StoredSnapshot(value, json_revision(raw))

    def save(
        self,
        settings: SettingsDocument,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[SettingsDocument]:
        with self._lock:
            self._ensure_open()
            current_raw = self._read_raw() if self._path.exists() else {}
            current_revision = json_revision(current_raw) if self._path.exists() else MISSING_REVISION
            if expected_revision is not None and expected_revision != current_revision:
                raise RepositoryConflict("设置已被其他操作修改，请重新加载")
            # 未知字段采用前向兼容保留策略；调用方省略字段不会静默删除已有数据。
            payload = {
                **copy.deepcopy(self._defaults),
                **copy.deepcopy(current_raw),
                **copy.deepcopy(settings),
            }
            try:
                self._validate_document(payload)
            except ValueError as error:
                raise RepositoryCorrupt("待保存 settings 未通过校验") from error
            self._writer.write(
                self._path,
                payload,
                validator=self._validate_document,
                backup_policy=self._backup_policy,
                backup_kind="settings",
            )
            return self.load()

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RepositoryClosed("SettingsRepository 已关闭")

    def _read_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            raise RepositoryUnavailable("settings 目标不是普通文件")
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RepositoryCorrupt("settings.json 无法读取或 JSON 已损坏") from error
        try:
            self._validate_document(value)
        except ValueError as error:
            raise RepositoryCorrupt("settings.json Schema 无效") from error
        return value

    @staticmethod
    def _validate_document(value: Any) -> None:
        if not isinstance(value, dict):
            raise ValueError("settings 顶层必须是对象")
        if any(not isinstance(key, str) or not key for key in value):
            raise ValueError("settings 键必须是非空字符串")
        if "data_root" in value:
            raise ValueError("data_root 不得写入用户目录内 settings")
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("settings 包含不可序列化值") from error
