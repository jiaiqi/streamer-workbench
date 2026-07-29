"""SongRepository 的 JSON 文件 adapter。"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.data.songs import Song, SongLibrary
from server.ports.repositories import (
    BackupPolicy,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryUnavailable,
    StoredSnapshot,
)
from server.repositories.atomic_json import AtomicJsonWriter, MISSING_REVISION, json_revision


class FileSongRepository:
    """显式路径、实例私有锁和 revision/CAS 的歌曲库 adapter。"""

    def __init__(
        self,
        path: Path,
        backup_policy: BackupPolicy,
        writer: AtomicJsonWriter | None = None,
    ):
        self._path = Path(path).expanduser().resolve()
        self._backup_policy = backup_policy
        self._writer = writer or AtomicJsonWriter()
        self._lock = threading.RLock()
        self._closed = False

    def load(self) -> StoredSnapshot[SongLibrary]:
        with self._lock:
            self._ensure_open()
            if not self._path.exists():
                return StoredSnapshot(SongLibrary(), MISSING_REVISION)
            raw = self._read_raw()
            library = self._decode(raw)
            return StoredSnapshot(copy.deepcopy(library), json_revision(raw))

    def save(
        self,
        library: SongLibrary,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[SongLibrary]:
        with self._lock:
            self._ensure_open()
            current_revision = self._current_revision()
            if expected_revision is not None and expected_revision != current_revision:
                raise RepositoryConflict("歌曲库已被其他操作修改，请重新加载")
            detached = copy.deepcopy(library)
            payload = {
                "version": SongLibrary.CURRENT_VERSION,
                "songs": [asdict(song) for song in detached.songs],
            }
            try:
                SongLibrary._validate_v5(copy.deepcopy(payload))
            except (TypeError, ValueError, AttributeError) as error:
                raise RepositoryCorrupt("待保存歌曲库未通过 v5 校验") from error
            self._writer.write(
                self._path,
                payload,
                validator=self._validate_payload,
                backup_policy=self._backup_policy,
                backup_kind="songs",
            )
            # 必须从发布后的目标重读，返回值不共享调用者的可变对象。
            return self.load()

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RepositoryClosed("SongRepository 已关闭")

    def _current_revision(self) -> str:
        if not self._path.exists():
            return MISSING_REVISION
        return json_revision(self._read_raw())

    def _read_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            raise RepositoryUnavailable("歌曲库目标不是普通文件")
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RepositoryCorrupt("songs.json 无法读取或 JSON 已损坏") from error
        if not isinstance(value, dict):
            raise RepositoryCorrupt("songs.json 顶层必须是对象")
        return value

    @staticmethod
    def _decode(raw: dict[str, Any]) -> SongLibrary:
        try:
            migrated = SongLibrary._migrate(copy.deepcopy(raw))
            songs = [
                Song(**{
                    key: value
                    for key, value in item.items()
                    if key in Song.__dataclass_fields__
                })
                for item in migrated.get("songs", [])
            ]
            return SongLibrary(songs)
        except (TypeError, ValueError, AttributeError) as error:
            raise RepositoryCorrupt("歌曲库 Schema 无效或无法迁移") from error

    @classmethod
    def _validate_payload(cls, value: Any) -> None:
        try:
            if not isinstance(value, dict):
                raise ValueError("歌曲库顶层必须是对象")
            if value.get("version") != SongLibrary.CURRENT_VERSION:
                raise ValueError("歌曲库发布版本必须是 v5")
            SongLibrary._validate_v5(copy.deepcopy(value))
            cls._decode(value)
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("歌曲库 payload 无效") from error
