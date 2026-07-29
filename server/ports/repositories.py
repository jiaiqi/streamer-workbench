"""Repository ports 与不依赖 FastAPI 的共享可靠性类型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Iterator, Literal, Protocol, TypeAlias, TypeVar

from core.data.songs import SongLibrary
from core.data.presets import Preset


T = TypeVar("T")
SettingsDocument: TypeAlias = dict[str, Any]
EventRecord: TypeAlias = dict[str, Any]
EventV2: TypeAlias = dict[str, Any]
MISSING_REVISION = "missing"


@dataclass(frozen=True)
class StoredSnapshot(Generic[T]):
    """脱离 adapter 内部状态的值快照及其不透明 revision。"""

    value: T
    revision: str


@dataclass(frozen=True)
class BackupPolicy:
    """单类 Repository 的备份目录和保留策略。"""

    root: Path
    keep: int = 20
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.keep < 0:
            raise ValueError("backup keep 不能为负数")
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())


@dataclass(frozen=True)
class EventQuery:
    event_type: str | None = None
    since: str | None = None
    until: str | None = None


@dataclass(frozen=True)
class AppendResult:
    status: Literal["appended", "already_exists"]
    event: EventRecord


@dataclass(frozen=True)
class RecoveryReport:
    detected: tuple[str, ...] = ()
    recovered: tuple[str, ...] = ()
    quarantined: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True)
class PresetSummary:
    id: str
    name: str
    layout_id: str
    is_default: bool
    created_at: str
    updated_at: str


class RepositoryError(Exception):
    """Repository 可稳定映射的基础错误。"""


class RepositoryNotFound(RepositoryError):
    pass


class RepositoryConflict(RepositoryError):
    pass


class RepositoryCorrupt(RepositoryError):
    pass


class RepositoryUnavailable(RepositoryError):
    pass


class RepositoryRecoveryRequired(RepositoryError):
    pass


class RepositoryClosed(RepositoryUnavailable):
    pass


class SongRepository(Protocol):
    def load(self) -> StoredSnapshot[SongLibrary]: ...

    def save(
        self,
        library: SongLibrary,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[SongLibrary]: ...

    def close(self) -> None: ...


class SettingsRepository(Protocol):
    def load(self) -> StoredSnapshot[SettingsDocument]: ...

    def save(
        self,
        settings: SettingsDocument,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[SettingsDocument]: ...

    def close(self) -> None: ...


class PresetRepository(Protocol):
    def list(self) -> StoredSnapshot[tuple[PresetSummary, ...]]: ...

    def get(self, preset_id: str) -> StoredSnapshot[Preset] | None: ...

    def save(
        self,
        preset: Preset,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[Preset]: ...

    def rename(
        self,
        preset_id: str,
        name: str,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[Preset]: ...

    def delete(self, preset_id: str, *, expected_revision: str | None) -> bool: ...

    def duplicate(self, source_id: str, target: Preset) -> StoredSnapshot[Preset]: ...

    def set_default(
        self,
        preset_id: str,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[tuple[PresetSummary, ...]]: ...

    def recover(self) -> RecoveryReport: ...

    def close(self) -> None: ...


class EventStore(Protocol):
    @property
    def recovery_report(self) -> RecoveryReport: ...

    def append(self, event: EventV2) -> AppendResult: ...

    def get_by_id(self, event_id: str) -> EventV2 | None: ...

    def iter(self, query: EventQuery) -> Iterator[EventRecord]: ...

    def tail(
        self,
        *,
        limit: int,
        event_type: str | None = None,
    ) -> tuple[EventRecord, ...]: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...
