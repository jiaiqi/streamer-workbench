"""带启动索引、尾行恢复和幂等追加的 JSONL EventStore。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.ports.repositories import (
    AppendResult,
    EventQuery,
    EventRecord,
    EventV2,
    RecoveryReport,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
)
from server.repositories.atomic_json import _fsync_directory


_SEMANTIC_KEYS = (
    "schema_version",
    "event_id",
    "occurred_at",
    "type",
    "source",
    "song_id",
    "title_snapshot",
    "meta",
)


@dataclass(frozen=True)
class _IndexEntry:
    offset: int
    length: int
    fingerprint: str


@dataclass(frozen=True)
class _FileState:
    device: int
    inode: int
    size: int
    modified_ns: int


class EventFaultInjector:
    """EventStore 测试故障注入器。"""

    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at

    def __call__(self, phase: str) -> None:
        if phase == self.fail_at:
            raise OSError(f"injected failure at {phase}")


class FileEventStore:
    """显式 Path、实例私有索引与锁的 JSONL 事件存储。"""

    def __init__(
        self,
        path: Path,
        fault_injector: Callable[[str], None] | None = None,
    ):
        self._path = Path(path).expanduser().resolve()
        self._inject = fault_injector or (lambda _phase: None)
        self._lock = threading.RLock()
        self._closed = False
        self._index: dict[str, _IndexEntry] = {}
        self._state: _FileState | None = None
        self._recovery_report = RecoveryReport()
        with self._lock:
            self._rebuild_index(allow_tail_recovery=True)

    @property
    def recovery_report(self) -> RecoveryReport:
        with self._lock:
            return self._recovery_report

    @property
    def index_size(self) -> int:
        with self._lock:
            return len(self._index)

    def append(self, event: EventV2) -> AppendResult:
        with self._lock:
            self._ensure_open()
            self._ensure_current()
            detached = copy.deepcopy(event)
            self._validate_v2(detached)
            event_id = detached["event_id"]
            fingerprint = self._fingerprint(detached)
            existing_entry = self._index.get(event_id)
            if existing_entry is not None:
                existing = self._read_indexed(existing_entry)
                if existing_entry.fingerprint != fingerprint:
                    raise RepositoryConflict(f"event_id 冲突且事件内容不同：{event_id}")
                return AppendResult("already_exists", copy.deepcopy(existing))

            try:
                serialized = json.dumps(
                    detached,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8") + b"\n"
            except (TypeError, ValueError) as error:
                raise RepositoryCorrupt("Event v2 包含不可序列化值") from error
            if b"\n" in serialized[:-1] or b"\r" in serialized[:-1]:
                raise RepositoryCorrupt("Event v2 序列化后不得包含物理换行")

            self._path.parent.mkdir(parents=True, exist_ok=True)
            offset = self._path.stat().st_size if self._path.exists() else 0
            descriptor: int | None = None
            try:
                descriptor = os.open(
                    self._path,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                    0o600,
                )
                self._inject("before_write")
                written = 0
                while written < len(serialized):
                    count = os.write(descriptor, serialized[written:])
                    if count <= 0:
                        raise OSError("event append returned zero bytes")
                    written += count
                self._inject("after_write")
                self._inject("before_fsync")
                os.fsync(descriptor)
                self._inject("after_fsync")
            except OSError as error:
                raise RepositoryUnavailable("Event JSONL 追加失败；索引未更新") from error
            finally:
                if descriptor is not None:
                    os.close(descriptor)

            try:
                self._inject("before_index_update")
            except OSError as error:
                raise RepositoryUnavailable("事件已刷盘但索引尚未更新；重试将重建索引") from error
            self._index[event_id] = _IndexEntry(offset, len(serialized), fingerprint)
            self._state = self._capture_state()
            return AppendResult("appended", copy.deepcopy(detached))

    def get_by_id(self, event_id: str) -> EventV2 | None:
        with self._lock:
            self._ensure_open()
            self._ensure_current()
            entry = self._index.get(event_id)
            return copy.deepcopy(self._read_indexed(entry)) if entry else None

    def iter(self, query: EventQuery) -> Iterator[EventRecord]:
        with self._lock:
            self._ensure_open()
            self._ensure_current()
            events = tuple(
                copy.deepcopy(event)
                for _offset, _length, event in self._scan_records()
                if self._matches(event, query)
            )
        return iter(events)

    def tail(
        self,
        *,
        limit: int,
        event_type: str | None = None,
    ) -> tuple[EventRecord, ...]:
        if limit < 1:
            raise ValueError("limit 必须大于 0")
        events = tuple(self.iter(EventQuery(event_type=event_type)))
        return tuple(reversed(events[-limit:]))

    def flush(self) -> None:
        with self._lock:
            self._ensure_open()
            self._ensure_current()

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RepositoryClosed("EventStore 已关闭")

    def _ensure_current(self) -> None:
        current = self._capture_state()
        if current == self._state:
            return
        if self._state is None and current is not None:
            self._rebuild_index(allow_tail_recovery=True)
            return
        if self._state is None or current is None:
            raise RepositoryConflict("events.jsonl 被外部创建或删除")
        same_file = (current.device, current.inode) == (self._state.device, self._state.inode)
        if same_file and current.size > self._state.size:
            self._rebuild_index(allow_tail_recovery=True)
            return
        if same_file and current.size == self._state.size and current.modified_ns == self._state.modified_ns:
            self._state = current
            return
        raise RepositoryConflict("events.jsonl 被外部替换、收缩或原地修改")

    def _rebuild_index(self, *, allow_tail_recovery: bool) -> None:
        if not self._path.exists():
            self._index = {}
            self._state = None
            return
        if not self._path.is_file():
            raise RepositoryRecoveryRequired("events.jsonl 不是普通文件")
        try:
            data = self._path.read_bytes()
        except OSError as error:
            raise RepositoryUnavailable("events.jsonl 无法读取") from error

        if data and not data.endswith(b"\n"):
            start = data.rfind(b"\n") + 1
            tail = data[start:]
            if self._valid_standalone_line(tail):
                if not allow_tail_recovery:
                    raise RepositoryRecoveryRequired("events.jsonl 尾行缺少换行")
                self._append_missing_newline()
                self._merge_report(
                    detected=("complete_tail_without_newline",),
                    recovered=("appended_missing_newline",),
                )
                data += b"\n"
            else:
                if not allow_tail_recovery:
                    raise RepositoryRecoveryRequired("events.jsonl 存在截断尾行")
                quarantine_name = self._quarantine_and_truncate_tail(tail, start)
                self._merge_report(
                    detected=("truncated_tail",),
                    recovered=("truncated_to_last_valid_newline",),
                    quarantined=(quarantine_name,),
                )
                data = data[:start]

        index: dict[str, _IndexEntry] = {}
        duplicate_ids: list[str] = []
        offset = 0
        for line_number, raw_line in enumerate(data.splitlines(keepends=True), start=1):
            length = len(raw_line)
            content = raw_line.rstrip(b"\r\n")
            if not content.strip():
                offset += length
                continue
            event = self._parse_record(content, line_number)
            if event.get("schema_version") == 2:
                event_id = event["event_id"]
                fingerprint = self._fingerprint(event)
                existing = index.get(event_id)
                if existing is not None:
                    if existing.fingerprint != fingerprint:
                        raise RepositoryRecoveryRequired(
                            f"events.jsonl 第 {line_number} 行 event_id 冲突：{event_id}",
                        )
                    duplicate_ids.append(event_id)
                else:
                    index[event_id] = _IndexEntry(offset, length, fingerprint)
            offset += length
        if duplicate_ids:
            self._merge_report(detected=tuple(f"duplicate_event_id:{item}" for item in duplicate_ids))
        self._index = index
        self._state = self._capture_state()

    def _scan_records(self) -> Iterator[tuple[int, int, EventRecord]]:
        if not self._path.exists():
            return
        offset = 0
        with self._path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                length = len(raw_line)
                content = raw_line.rstrip(b"\r\n")
                if content.strip():
                    yield offset, length, self._parse_record(content, line_number)
                offset += length

    def _read_indexed(self, entry: _IndexEntry) -> EventV2:
        try:
            with self._path.open("rb") as handle:
                handle.seek(entry.offset)
                content = handle.read(entry.length).rstrip(b"\r\n")
            event = self._parse_record(content, line_number=None)
        except OSError as error:
            raise RepositoryUnavailable("无法读取已索引事件") from error
        if event.get("schema_version") != 2:
            raise RepositoryRecoveryRequired("EventStore 索引指向非 v2 事件")
        return event

    @classmethod
    def _parse_record(cls, content: bytes, line_number: int | None) -> EventRecord:
        location = f"第 {line_number} 行" if line_number is not None else "索引位置"
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RepositoryRecoveryRequired(f"events.jsonl {location}包含非法 UTF-8") from error
        try:
            event = json.loads(text)
        except json.JSONDecodeError as error:
            raise RepositoryRecoveryRequired(f"events.jsonl {location}包含损坏 JSON") from error
        if not isinstance(event, dict):
            raise RepositoryRecoveryRequired(f"events.jsonl {location}顶层不是对象")
        version = event.get("schema_version", 1)
        if version == 2:
            try:
                cls._validate_v2(event)
            except RepositoryCorrupt as error:
                raise RepositoryRecoveryRequired(f"events.jsonl {location}包含非法 Event v2") from error
        elif version != 1:
            raise RepositoryRecoveryRequired(f"events.jsonl {location}包含不支持的 Schema v{version}")
        elif not isinstance(event.get("type"), str) or not event["type"].strip():
            raise RepositoryRecoveryRequired(f"events.jsonl {location}包含非法 Event v1")
        return event

    @classmethod
    def _valid_standalone_line(cls, content: bytes) -> bool:
        try:
            cls._parse_record(content, line_number=None)
            return True
        except RepositoryRecoveryRequired:
            return False

    @staticmethod
    def _validate_v2(event: Any) -> None:
        if not isinstance(event, dict) or event.get("schema_version") != 2:
            raise RepositoryCorrupt("Event 必须是 Schema v2 对象")
        required = ("event_id", "occurred_at", "recorded_at", "type", "source")
        if any(not isinstance(event.get(key), str) or not event[key].strip() for key in required):
            raise RepositoryCorrupt("Event v2 缺少非空身份、时间、类型或来源")
        if not event["event_id"].startswith("evt_"):
            raise RepositoryCorrupt("Event v2 event_id 格式无效")
        for key in ("song_id", "title_snapshot"):
            if key in event and not isinstance(event[key], str):
                raise RepositoryCorrupt(f"Event v2 {key} 必须是字符串")
        if "meta" in event and not isinstance(event["meta"], dict):
            raise RepositoryCorrupt("Event v2 meta 必须是对象")

    @staticmethod
    def _fingerprint(event: EventRecord) -> str:
        semantic = {key: event.get(key) for key in _SEMANTIC_KEYS}
        try:
            content = json.dumps(
                semantic,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise RepositoryCorrupt("Event v2 无法计算语义摘要") from error
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _matches(event: EventRecord, query: EventQuery) -> bool:
        if query.event_type and event.get("type") != query.event_type:
            return False
        occurred_at = str(event.get("occurred_at") or event.get("ts") or "")
        if query.since and occurred_at < query.since:
            return False
        if query.until and occurred_at > query.until:
            return False
        return True

    def _append_missing_newline(self) -> None:
        try:
            descriptor = os.open(self._path, os.O_APPEND | os.O_WRONLY)
            try:
                os.write(descriptor, b"\n")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise RepositoryRecoveryRequired("无法修复 events.jsonl 缺失换行") from error

    def _quarantine_and_truncate_tail(self, tail: bytes, truncate_at: int) -> str:
        recovery_dir = self._path.parent / f".{self._path.name}.recovery"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        name = f"tail-{timestamp}-{uuid.uuid4().hex[:8]}.bin"
        quarantine = recovery_dir / name
        try:
            with quarantine.open("xb") as handle:
                handle.write(tail)
                handle.flush()
                os.fsync(handle.fileno())
            if quarantine.read_bytes() != tail:
                raise OSError("quarantine verification failed")
            with self._path.open("r+b") as handle:
                handle.truncate(truncate_at)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(self._path.parent)
        except OSError as error:
            raise RepositoryRecoveryRequired("无法隔离并截断 events.jsonl 尾行") from error
        return name

    def _capture_state(self) -> _FileState | None:
        try:
            stat = self._path.stat()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise RepositoryUnavailable("无法读取 events.jsonl 文件状态") from error
        return _FileState(stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

    def _merge_report(
        self,
        *,
        detected: tuple[str, ...] = (),
        recovered: tuple[str, ...] = (),
        quarantined: tuple[str, ...] = (),
        unresolved: tuple[str, ...] = (),
    ) -> None:
        current = self._recovery_report
        self._recovery_report = RecoveryReport(
            detected=current.detected + detected,
            recovered=current.recovered + recovered,
            quarantined=current.quarantined + quarantined,
            unresolved=current.unresolved + unresolved,
        )
