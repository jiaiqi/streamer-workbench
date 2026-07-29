"""曲谱附件应用服务：协调文件、歌曲元数据与事件的可恢复事务。"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.data.events import _normalize_timestamp
from core.data.tabs import ALLOWED_EXT, MAX_FILE_BYTES, SONG_ID_RE, sanitize_name
from server.ports.repositories import BackupPolicy, RepositoryRecoveryRequired
from server.repositories.atomic_json import AtomicJsonWriter, _fsync_directory


_ROOT_LOCKS_GUARD = threading.Lock()
_ROOT_LOCKS: dict[Path, threading.RLock] = {}
_TRANSACTION_ID_RE = re.compile(r"^tabtx_[0-9a-f]{32}$")
_EVENT_ID_RE = re.compile(r"^evt_[0-9a-f]{32}$")


def _root_lock(path: Path) -> threading.RLock:
    """同一进程内，相同数据根的多个 AppContext 共用一把事务锁。"""
    with _ROOT_LOCKS_GUARD:
        return _ROOT_LOCKS.setdefault(path, threading.RLock())


class TabServiceError(Exception):
    """可由 HTTP 适配层稳定映射的曲谱用例错误。"""


class TabValidationFailed(TabServiceError):
    pass


class TabNotFound(TabServiceError):
    pass


class TabRecoveryRequired(RepositoryRecoveryRequired):
    """业务状态已提交但恢复日志仍需在下次启动继续。"""


@dataclass(frozen=True)
class TabListing:
    song_id: str
    title: str
    tab_files: tuple[str, ...]


@dataclass(frozen=True)
class TabUploadResult(TabListing):
    file: str


@dataclass(frozen=True)
class TabRecoveryReport:
    committed: tuple[str, ...] = ()
    rolled_back: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


class TabApplicationService:
    """以 journal 驱动曲谱文件与 Song.tab_files 的一致提交和启动恢复。"""

    def __init__(
        self,
        *,
        song_repository,
        event_store,
        tabs_root: Path,
        transactions_root: Path,
        fault_injector: Callable[[str], None] | None = None,
    ):
        self._songs = song_repository
        self._events = event_store
        self._tabs_root = Path(tabs_root).expanduser().resolve()
        self._transactions_root = Path(transactions_root).expanduser().resolve()
        self._inject = fault_injector or (lambda _phase: None)
        self._lock = _root_lock(self._transactions_root)
        self._journal_writer = AtomicJsonWriter()
        self._journal_policy = BackupPolicy(
            self._transactions_root / ".journal-backups",
            keep=0,
            enabled=False,
        )

    def list(self, identity: str) -> TabListing:
        snapshot = self._songs.load()
        song = self._find(snapshot.value, identity)
        return self._listing(song)

    def upload(
        self,
        identity: str,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> TabUploadResult:
        with self._lock:
            snapshot = self._songs.load()
            song = self._find(snapshot.value, identity)
            relative_path = self._allocate_relative_path(
                song.id, filename, data, content_type)
            event = self._event(
                song.id,
                song.title,
                {"changes": [{"field": "tab_files", "old": None,
                               "new": relative_path}]},
            )
            journal = self._prepare(
                "upload", song.id, song.title, relative_path, event, data)
            try:
                self._publish_upload(journal)
            except Exception:
                self._rollback_upload(journal)
                raise
            self._inject("after_file_publish")
            old_library = copy.deepcopy(snapshot.value)
            song.tab_files.append(relative_path)
            try:
                saved = self._songs.save(
                    snapshot.value, expected_revision=snapshot.revision)
            except Exception:
                self._rollback_upload(journal)
                raise
            self._set_phase(journal, "metadata_published",
                            metadata_revision=saved.revision)
            self._inject("after_metadata_publish")
            try:
                self._events.append(event)
            except Exception as error:
                # 元数据已经发布；保留 journal，让启动恢复以固定 event_id 幂等补报。
                raise TabRecoveryRequired(
                    "曲谱已保存，事件将在下次启动时自动补报") from error
            self._set_phase(journal, "committed")
            current = saved.value.get_by_id(song.id)
            if current is None:
                # 理论上不会发生；保留 before image 便于诊断。
                self._restore_library(old_library, saved.revision, journal)
                raise TabRecoveryRequired("曲谱提交后歌曲身份丢失")
            listing = self._listing(current)
            return TabUploadResult(
                listing.song_id, listing.title, listing.tab_files,
                relative_path)

    def delete(self, identity: str, relative_path: str) -> TabListing:
        with self._lock:
            snapshot = self._songs.load()
            song = self._find(snapshot.value, identity)
            if relative_path not in song.tab_files:
                raise TabNotFound(f"曲谱不存在：{relative_path}")
            self._validate_relative_path(song.id, relative_path)
            event = self._event(
                song.id,
                song.title,
                {"changes": [{"field": "tab_files", "old": relative_path,
                               "new": None}]},
            )
            journal = self._prepare(
                "delete", song.id, song.title, relative_path, event)
            try:
                self._stage_delete(journal)
            except Exception:
                self._rollback_delete(journal)
                raise
            self._inject("after_file_stage")
            song.tab_files.remove(relative_path)
            try:
                saved = self._songs.save(
                    snapshot.value, expected_revision=snapshot.revision)
            except Exception:
                self._rollback_delete(journal)
                raise
            self._set_phase(journal, "metadata_published",
                            metadata_revision=saved.revision)
            self._inject("after_metadata_publish")
            try:
                self._events.append(event)
            except Exception as error:
                raise TabRecoveryRequired(
                    "曲谱已移入可恢复区，事件将在下次启动时自动补报") from error
            self._set_phase(journal, "committed")
            current = saved.value.get_by_id(song.id)
            if current is None:
                raise TabRecoveryRequired("曲谱删除提交后歌曲身份丢失")
            return self._listing(current)

    def recover(self) -> TabRecoveryReport:
        with self._lock:
            if not self._transactions_root.is_dir():
                return TabRecoveryReport()
            committed: list[str] = []
            rolled_back: list[str] = []
            unresolved: list[str] = []
            for directory in sorted(self._transactions_root.iterdir()):
                if not directory.is_dir() or directory.name.startswith("."):
                    continue
                try:
                    journal = self._read_journal(directory)
                    phase = journal.get("phase")
                    if phase in ("committed", "rolled_back"):
                        continue
                    outcome = self._recover_one(journal)
                    (committed if outcome == "committed" else rolled_back).append(
                        journal["transaction_id"])
                except Exception:
                    unresolved.append(directory.name)
            return TabRecoveryReport(
                tuple(committed), tuple(rolled_back), tuple(unresolved))

    def _recover_one(self, journal: dict[str, Any]) -> str:
        snapshot = self._songs.load()
        song = snapshot.value.get_by_id(journal["song_id"])
        relative_path = journal["relative_path"]
        operation = journal["operation"]
        phase = journal["phase"]
        metadata_has_path = song is not None and relative_path in song.tab_files
        target_exists = self._target(
            journal["song_id"], relative_path).is_file()
        staged_exists = (
            self._transaction_dir(journal) / "content").is_file()
        state = (phase, metadata_has_path, staged_exists, target_exists)
        if operation == "upload":
            commit_states = {
                ("file_published", True, False, True),
                ("metadata_published", True, False, True),
            }
            rollback_states = {
                ("prepared", False, True, False),
                ("prepared", False, False, True),
                ("file_published", False, False, True),
            }
            if state in commit_states:
                self._events.append(journal["event"])
                self._set_phase(journal, "committed")
                return "committed"
            if state in rollback_states:
                self._rollback_upload(journal)
                return "rolled_back"
        if operation == "delete":
            commit_states = {
                ("file_staged", False, True, False),
                ("metadata_published", False, True, False),
            }
            rollback_states = {
                ("prepared", True, False, True),
                ("prepared", True, True, False),
                ("file_staged", True, True, False),
            }
            if state in commit_states:
                self._events.append(journal["event"])
                self._set_phase(journal, "committed")
                return "committed"
            if state in rollback_states:
                self._rollback_delete(journal)
                return "rolled_back"
        raise TabRecoveryRequired(
            "曲谱事务物理状态与阶段矛盾："
            f"operation={operation}, phase={phase}, metadata={metadata_has_path}, "
            f"staged={staged_exists}, target={target_exists}")

    def _prepare(
        self,
        operation: str,
        song_id: str,
        title: str,
        relative_path: str,
        event: dict[str, Any],
        content: bytes | None = None,
    ) -> dict[str, Any]:
        transaction_id = f"tabtx_{uuid.uuid4().hex}"
        directory = self._transactions_root / transaction_id
        directory.mkdir(parents=True, exist_ok=False)
        _fsync_directory(directory.parent)
        if content is not None:
            self._write_content(directory / "content", content)
        journal = {
            "schema_version": 1,
            "transaction_id": transaction_id,
            "operation": operation,
            "phase": "prepared",
            "song_id": song_id,
            "title_snapshot": title,
            "relative_path": relative_path,
            "event": event,
            "created_at": datetime.now().astimezone().isoformat(
                timespec="seconds"),
        }
        self._write_journal(directory, journal)
        return journal

    def _publish_upload(self, journal: dict[str, Any]) -> None:
        directory = self._transaction_dir(journal)
        staged = directory / "content"
        target = self._target(journal["song_id"], journal["relative_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise TabValidationFailed(f"曲谱目标已存在：{journal['relative_path']}")
        os.replace(staged, target)
        _fsync_directory(target.parent)
        self._set_phase(journal, "file_published")

    def _stage_delete(self, journal: dict[str, Any]) -> None:
        source = self._target(journal["song_id"], journal["relative_path"])
        if not source.is_file():
            raise TabNotFound(f"曲谱文件不存在：{journal['relative_path']}")
        staged = self._transaction_dir(journal) / "content"
        os.replace(source, staged)
        _fsync_directory(source.parent)
        self._set_phase(journal, "file_staged")

    def _rollback_upload(self, journal: dict[str, Any]) -> None:
        target = self._target(journal["song_id"], journal["relative_path"])
        staged = self._transaction_dir(journal) / "content"
        recovered = self._transaction_dir(journal) / "rolled-back-content"
        if staged.is_file():
            # prepared 阶段尚未发布，不能触碰可能由并发操作创建的同名目标。
            os.replace(staged, recovered)
        elif target.is_file():
            # content 已离开事务目录，说明目标是本事务发布的文件。
            os.replace(target, recovered)
            _fsync_directory(target.parent)
        self._set_phase(journal, "rolled_back")

    def _rollback_delete(self, journal: dict[str, Any]) -> None:
        staged = self._transaction_dir(journal) / "content"
        target = self._target(journal["song_id"], journal["relative_path"])
        if staged.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise TabRecoveryRequired(
                    f"无法恢复曲谱，目标已存在：{journal['relative_path']}")
            os.replace(staged, target)
            _fsync_directory(target.parent)
        self._set_phase(journal, "rolled_back")

    def _restore_library(
        self, old_library, expected_revision: str, journal: dict[str, Any]
    ) -> None:
        try:
            self._songs.save(
                old_library, expected_revision=expected_revision)
            self._rollback_upload(journal)
        except Exception as error:
            raise TabRecoveryRequired("歌曲元数据回滚失败，需要启动恢复") from error

    def _allocate_relative_path(
        self, song_id: str, filename: str, data: bytes,
        content_type: str | None = None,
    ) -> str:
        if not SONG_ID_RE.fullmatch(song_id or ""):
            raise TabValidationFailed(f"非法 song_id：{song_id!r}")
        extension = Path(filename or "").suffix.lower()
        if extension not in ALLOWED_EXT:
            raise TabValidationFailed(
                f"不支持的文件类型：{extension or '（无扩展名）'}"
                f"（允许 {sorted(ALLOWED_EXT)}）")
        if len(data) > MAX_FILE_BYTES:
            raise TabValidationFailed(
                f"文件超过 {MAX_FILE_BYTES // 1024 // 1024}MB 上限")
        mime_by_extension = {
            ".png": {"image/png"},
            ".jpg": {"image/jpeg"},
            ".jpeg": {"image/jpeg"},
            ".webp": {"image/webp"},
            ".gif": {"image/gif"},
            ".pdf": {"application/pdf"},
        }
        normalized_mime = (content_type or "").split(";", 1)[0].strip().lower()
        if (normalized_mime and normalized_mime != "application/octet-stream"
                and normalized_mime not in mime_by_extension[extension]):
            raise TabValidationFailed(
                f"文件 MIME 与扩展名不匹配：{normalized_mime}")
        base = sanitize_name(Path(filename).stem)
        directory = self._tabs_root / song_id
        candidate = f"{base}{extension}"
        index = 1
        while (directory / candidate).exists():
            candidate = f"{base}-{index}{extension}"
            index += 1
        return f"tabs/{song_id}/{candidate}"

    def _validate_relative_path(self, song_id: str, relative_path: str) -> None:
        prefix = f"tabs/{song_id}/"
        if (not relative_path.startswith(prefix) or ".." in relative_path
                or Path(relative_path).name != relative_path[len(prefix):]):
            raise TabValidationFailed("曲谱路径不属于当前歌曲")

    def _target(self, song_id: str, relative_path: str) -> Path:
        self._validate_relative_path(song_id, relative_path)
        directory = self._tabs_root / song_id
        if directory.is_symlink():
            raise TabValidationFailed("曲谱目录不得是符号链接")
        target = directory / Path(relative_path).name
        if target.is_symlink():
            raise TabValidationFailed("曲谱文件不得是符号链接")
        try:
            target.resolve(strict=False).relative_to(self._tabs_root)
        except ValueError as error:
            raise TabValidationFailed("曲谱路径逃逸数据目录") from error
        return target

    @staticmethod
    def _find(library, identity: str):
        song = library.get_by_id(identity) or library.get(identity)
        if song is None:
            raise TabNotFound(f"未找到歌曲：{identity}")
        return song

    @staticmethod
    def _listing(song) -> TabListing:
        return TabListing(song.id, song.title, tuple(song.tab_files))

    @staticmethod
    def _event(song_id: str, title: str, meta: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        return {
            "schema_version": 2,
            "event_id": f"evt_{uuid.uuid4().hex}",
            "occurred_at": _normalize_timestamp(None),
            "recorded_at": now,
            "type": "song_edited",
            "source": "tabs-api",
            "song_id": song_id,
            "title_snapshot": title,
            "meta": meta,
        }

    def _set_phase(self, journal: dict[str, Any], phase: str, **values) -> None:
        journal.update(values)
        journal["phase"] = phase
        journal["updated_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds")
        self._write_journal(self._transaction_dir(journal), journal)

    def _write_journal(self, directory: Path, journal: dict[str, Any]) -> None:
        self._journal_writer.write(
            directory / "journal.json",
            journal,
            validator=self._validate_journal,
            backup_policy=self._journal_policy,
            backup_kind="tab-journal",
        )

    @staticmethod
    def _validate_journal(value: Any) -> None:
        required = {
            "schema_version", "transaction_id", "operation", "phase",
            "song_id", "title_snapshot", "relative_path", "event",
        }
        if not isinstance(value, dict) or not required.issubset(value):
            raise ValueError("曲谱事务 journal 不完整")
        if value["schema_version"] != 1:
            raise ValueError("曲谱事务 journal 版本不受支持")
        if value["operation"] not in ("upload", "delete"):
            raise ValueError("曲谱事务操作无效")
        phases = {
            "upload": {"prepared", "file_published", "metadata_published",
                       "committed", "rolled_back"},
            "delete": {"prepared", "file_staged", "metadata_published",
                       "committed", "rolled_back"},
        }
        if value["phase"] not in phases[value["operation"]]:
            raise ValueError("曲谱事务阶段无效")
        song_id = value["song_id"]
        relative_path = value["relative_path"]
        if not isinstance(song_id, str) or not SONG_ID_RE.fullmatch(song_id):
            raise ValueError("曲谱事务 song_id 无效")
        prefix = f"tabs/{song_id}/"
        if (not isinstance(relative_path, str)
                or not relative_path.startswith(prefix)
                or Path(relative_path).name != relative_path[len(prefix):]
                or ".." in relative_path):
            raise ValueError("曲谱事务路径与 song_id 不一致")
        event = value["event"]
        if (not isinstance(event, dict)
                or event.get("schema_version") != 2
                or not _EVENT_ID_RE.fullmatch(str(event.get("event_id", "")))
                or event.get("type") != "song_edited"
                or event.get("source") != "tabs-api"
                or event.get("song_id") != song_id
                or event.get("title_snapshot") != value["title_snapshot"]):
            raise ValueError("曲谱事务事件身份不一致")
        for time_key in ("occurred_at", "recorded_at"):
            timestamp = event.get(time_key)
            if not isinstance(timestamp, str) or not timestamp.strip():
                raise ValueError("曲谱事务事件时间缺失")
            try:
                if datetime.fromisoformat(timestamp).tzinfo is None:
                    raise ValueError("事件时间必须包含时区")
            except ValueError as error:
                raise ValueError("曲谱事务事件时间无效") from error
        meta = event.get("meta")
        if not isinstance(meta, dict):
            raise ValueError("曲谱事务事件 meta 必须是对象")
        changes = meta.get("changes")
        expected_change = (
            {"field": "tab_files", "old": None, "new": relative_path}
            if value["operation"] == "upload"
            else {"field": "tab_files", "old": relative_path, "new": None}
        )
        if changes != [expected_change]:
            raise ValueError("曲谱事务事件变更与操作不一致")

    def _read_journal(self, directory: Path) -> dict[str, Any]:
        if directory.is_symlink():
            raise ValueError("曲谱事务目录不得是符号链接")
        path = directory / "journal.json"
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        self._validate_journal(value)
        if value["transaction_id"] != directory.name:
            raise ValueError("曲谱事务目录与 journal 身份不一致")
        return value

    def _transaction_dir(self, journal: dict[str, Any]) -> Path:
        transaction_id = journal["transaction_id"]
        if not isinstance(transaction_id, str) or not _TRANSACTION_ID_RE.fullmatch(
                transaction_id):
            raise ValueError("非法曲谱事务 ID")
        directory = self._transactions_root / transaction_id
        if directory.is_symlink():
            raise ValueError("曲谱事务目录不得是符号链接")
        return directory

    @staticmethod
    def _write_content(path: Path, content: bytes) -> None:
        descriptor, raw_temp = tempfile.mkstemp(
            prefix=".content.", suffix=".tmp", dir=path.parent)
        temporary = Path(raw_temp)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            _fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)
