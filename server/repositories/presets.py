"""带 journal 前滚恢复的 PresetRepository 文件 adapter。"""

from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.data import presets as preset_model
from core.data.presets import Preset
from server.ports.repositories import (
    BackupPolicy,
    PresetSummary,
    RecoveryReport,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
    StoredSnapshot,
)
from server.repositories.atomic_json import AtomicJsonWriter, MISSING_REVISION, json_revision


class PresetFaultInjector:
    """模拟进程在跨文件事务阶段崩溃。"""

    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at

    def __call__(self, phase: str) -> None:
        if phase == self.fail_at:
            raise OSError(f"injected preset crash at {phase}")


class FilePresetRepository:
    """manifest + item 全包提交、实例私有锁和启动恢复。"""

    def __init__(
        self,
        root: Path,
        backup_policy: BackupPolicy,
        *,
        writer: AtomicJsonWriter | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ):
        self._root = Path(root).expanduser().resolve()
        self._manifest_path = self._root / "manifest.json"
        self._transactions = self._root / ".transactions"
        self._trash = self._root / ".trash"
        self._backup_policy = backup_policy
        self._writer = writer or AtomicJsonWriter()
        self._inject = fault_injector or (lambda _phase: None)
        self._lock = threading.RLock()
        self._closed = False
        self._needs_recovery = False
        self._report = RecoveryReport()
        with self._lock:
            self.recover()

    def list(self) -> StoredSnapshot[tuple[PresetSummary, ...]]:
        with self._lock:
            manifest = self._ready_manifest()
            summaries = tuple(
                self._summary(preset_id, manifest[preset_id])
                for preset_id in sorted(
                    manifest,
                    key=lambda item: (manifest[item].get("updated_at", ""), item),
                    reverse=True,
                )
            )
            revision = json_revision(manifest) if self._manifest_path.exists() else MISSING_REVISION
            return StoredSnapshot(summaries, revision)

    def get(self, preset_id: str) -> StoredSnapshot[Preset] | None:
        with self._lock:
            manifest = self._ready_manifest()
            self._validate_id(preset_id)
            if preset_id not in manifest:
                return None
            payload = self._read_item_payload(preset_id)
            return StoredSnapshot(copy.deepcopy(self._decode(payload)), json_revision(payload))

    def save(
        self,
        preset: Preset,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[Preset]:
        with self._lock:
            return self._save_locked(preset, expected_revision=expected_revision, operation="save")

    def rename(
        self,
        preset_id: str,
        name: str,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[Preset]:
        with self._lock:
            current = self.get(preset_id)
            if current is None:
                raise RepositoryConflict(f"Preset 不存在：{preset_id}")
            renamed = copy.deepcopy(current.value)
            renamed.name = str(name).strip()
            if not renamed.name:
                raise RepositoryCorrupt("Preset 名称不能为空")
            return self._save_locked(renamed, expected_revision=expected_revision, operation="rename")

    def delete(self, preset_id: str, *, expected_revision: str | None) -> bool:
        with self._lock:
            manifest = self._ready_manifest()
            self._validate_id(preset_id)
            if preset_id not in manifest:
                return False
            payload = self._read_item_payload(preset_id)
            self._check_revision(expected_revision, json_revision(payload), "Preset")
            next_manifest = copy.deepcopy(manifest)
            next_manifest.pop(preset_id)
            self._commit("delete", {preset_id: None}, manifest, next_manifest)
            return True

    def duplicate(self, source_id: str, target: Preset) -> StoredSnapshot[Preset]:
        with self._lock:
            source = self.get(source_id)
            if source is None:
                raise RepositoryConflict(f"Preset 不存在：{source_id}")
            duplicate = copy.deepcopy(target)
            self._validate_id(duplicate.id)
            if self.get(duplicate.id) is not None:
                raise RepositoryConflict(f"目标 Preset 已存在：{duplicate.id}")
            now = datetime.now().isoformat(timespec="seconds")
            duplicate.created_at = duplicate.created_at or now
            duplicate.updated_at = now
            duplicate.is_default = False
            return self._save_locked(duplicate, expected_revision=MISSING_REVISION, operation="duplicate")

    def set_default(
        self,
        preset_id: str,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[tuple[PresetSummary, ...]]:
        with self._lock:
            manifest = self._ready_manifest()
            self._validate_id(preset_id)
            if preset_id not in manifest:
                raise RepositoryConflict(f"Preset 不存在：{preset_id}")
            manifest_revision = json_revision(manifest) if self._manifest_path.exists() else MISSING_REVISION
            self._check_revision(expected_revision, manifest_revision, "Preset 索引")
            now = datetime.now().isoformat(timespec="seconds")
            changes: dict[str, dict[str, Any] | None] = {}
            next_manifest = copy.deepcopy(manifest)
            for item_id in manifest:
                payload = self._read_item_payload(item_id)
                should_default = item_id == preset_id
                if payload.get("is_default") != should_default:
                    payload["is_default"] = should_default
                    payload["updated_at"] = now
                    changes[item_id] = payload
                next_manifest[item_id] = self._manifest_entry(payload)
            if changes:
                self._commit("set_default", changes, manifest, next_manifest)
            return self.list()

    def recover(self) -> RecoveryReport:
        with self._lock:
            self._ensure_open()
            if not self._root.exists():
                self._needs_recovery = False
                return self._report
            if not self._root.is_dir() or self._root.is_symlink():
                raise RepositoryRecoveryRequired("Preset 根目录不是安全普通目录")
            if self._transactions.exists():
                if not self._transactions.is_dir() or self._transactions.is_symlink():
                    raise RepositoryRecoveryRequired("Preset 事务目录不安全")
                for transaction_dir in sorted(self._transactions.iterdir()):
                    if not transaction_dir.is_dir() or transaction_dir.is_symlink():
                        raise RepositoryRecoveryRequired("Preset 事务目录包含未知条目")
                    self._recover_transaction(transaction_dir)
            self._validate_consistency(self._load_manifest())
            self._needs_recovery = False
            return self._report

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _save_locked(
        self,
        preset: Preset,
        *,
        expected_revision: str | None,
        operation: str,
    ) -> StoredSnapshot[Preset]:
        manifest = self._ready_manifest()
        detached = copy.deepcopy(preset)
        self._validate_id(detached.id)
        existing = self._read_item_payload(detached.id) if detached.id in manifest else None
        current_revision = json_revision(existing) if existing is not None else MISSING_REVISION
        self._check_revision(expected_revision, current_revision, "Preset")
        now = datetime.now().isoformat(timespec="seconds")
        detached.created_at = detached.created_at or now
        detached.updated_at = now
        payload = self._encode(detached)
        changes: dict[str, dict[str, Any] | None] = {detached.id: payload}
        next_manifest = copy.deepcopy(manifest)
        if detached.is_default:
            for item_id in manifest:
                if item_id == detached.id:
                    continue
                other = self._read_item_payload(item_id)
                if other.get("is_default"):
                    other["is_default"] = False
                    other["updated_at"] = now
                    changes[item_id] = other
                    next_manifest[item_id] = self._manifest_entry(other)
        next_manifest[detached.id] = self._manifest_entry(payload)
        self._commit(operation, changes, manifest, next_manifest)
        saved = self.get(detached.id)
        if saved is None:
            raise RepositoryRecoveryRequired("Preset 提交后无法读取")
        return saved

    def _commit(
        self,
        operation: str,
        changes: dict[str, dict[str, Any] | None],
        manifest_before: dict[str, Any],
        manifest_next: dict[str, Any],
    ) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._transactions.mkdir(parents=True, exist_ok=True)
        transaction_id = f"txn_{uuid.uuid4().hex}"
        transaction_dir = self._transactions / transaction_id
        transaction_dir.mkdir()
        disabled = BackupPolicy(transaction_dir / ".no-backups", keep=0, enabled=False)
        journal = {
            "version": 1,
            "transaction_id": transaction_id,
            "operation": operation,
            "phase": "staging",
            "item_ids": sorted(changes),
            "delete_ids": sorted(item_id for item_id, value in changes.items() if value is None),
        }
        try:
            self._stage_json(transaction_dir / "transaction.json", journal, disabled)
            self._stage_json(transaction_dir / "manifest.before.json", manifest_before, disabled)
            self._stage_json(transaction_dir / "manifest.next.json", manifest_next, disabled)
            for item_id, payload in changes.items():
                before = self._read_item_payload(item_id) if item_id in manifest_before else None
                if before is not None:
                    self._stage_json(transaction_dir / "before" / f"{item_id}.json", before, disabled)
                if payload is not None:
                    self._stage_json(transaction_dir / "next" / f"{item_id}.json", payload, disabled)
            self._inject("before_prepared")
            journal = self._set_phase(transaction_dir, journal, "prepared", disabled)
            self._inject("after_prepared")
            self._publish_items(transaction_dir, journal)
            journal = self._set_phase(transaction_dir, journal, "items_published", disabled)
            self._inject("after_items_publish")
            self._publish_manifest(transaction_dir)
            journal = self._set_phase(transaction_dir, journal, "manifest_published", disabled)
            self._inject("after_manifest_publish")
            self._validate_consistency(manifest_next)
            journal = self._set_phase(transaction_dir, journal, "committed", disabled)
            self._inject("after_committed")
            shutil.rmtree(transaction_dir)
        except BaseException as error:
            self._needs_recovery = True
            if isinstance(error, (RepositoryCorrupt, RepositoryRecoveryRequired, RepositoryUnavailable)):
                raise
            raise RepositoryUnavailable(
                f"Preset {operation} 事务中断；调用 recover 或重启后恢复",
            ) from error

    def _recover_transaction(self, transaction_dir: Path) -> None:
        journal_path = transaction_dir / "transaction.json"
        if not journal_path.is_file():
            raise RepositoryRecoveryRequired("Preset 事务缺少 journal")
        journal = self._read_json(journal_path, "Preset transaction")
        phase = journal.get("phase")
        transaction_id = journal.get("transaction_id", transaction_dir.name)
        if phase == "staging":
            shutil.rmtree(transaction_dir)
            self._merge_report(
                detected=(f"staging:{transaction_id}",),
                recovered=(f"kept_old:{transaction_id}",),
            )
            return
        if phase not in {"prepared", "items_published", "manifest_published", "committed"}:
            raise RepositoryRecoveryRequired(f"Preset 事务阶段未知：{phase}")
        manifest_next = self._read_json(transaction_dir / "manifest.next.json", "next manifest")
        if phase != "committed":
            self._publish_items(transaction_dir, journal)
            self._publish_manifest(transaction_dir)
            self._validate_consistency(manifest_next)
        else:
            active_manifest = self._load_manifest()
            if active_manifest != manifest_next:
                raise RepositoryRecoveryRequired("已提交 Preset 事务与活动 manifest 不一致")
            self._validate_consistency(active_manifest)
        shutil.rmtree(transaction_dir)
        self._merge_report(
            detected=(f"transaction:{transaction_id}:{phase}",),
            recovered=(f"completed_new:{transaction_id}",),
        )

    def _publish_items(self, transaction_dir: Path, journal: dict[str, Any]) -> None:
        transaction_id = str(journal["transaction_id"])
        delete_ids = set(journal.get("delete_ids", []))
        for item_id in journal.get("item_ids", []):
            self._validate_id(item_id)
            active_dir = self._item_dir(item_id)
            if item_id in delete_ids:
                trash_target = self._trash / f"{item_id}-{transaction_id}"
                if active_dir.exists() and trash_target.exists():
                    raise RepositoryRecoveryRequired("Preset 删除恢复发现活动项与 trash 同时存在")
                if active_dir.exists():
                    self._trash.mkdir(parents=True, exist_ok=True)
                    os.replace(active_dir, trash_target)
                continue
            payload = self._read_json(transaction_dir / "next" / f"{item_id}.json", "next preset")
            self._validate_payload(payload, expected_id=item_id)
            active_dir.mkdir(parents=True, exist_ok=True)
            if active_dir.is_symlink():
                raise RepositoryRecoveryRequired("Preset item 目录不得是符号链接")
            self._writer.write(
                active_dir / "preset.json",
                payload,
                validator=lambda value, item_id=item_id: self._validate_payload(value, expected_id=item_id),
                backup_policy=self._backup_policy,
                backup_kind=f"preset-{item_id}",
            )

    def _publish_manifest(self, transaction_dir: Path) -> None:
        manifest = self._read_json(transaction_dir / "manifest.next.json", "next manifest")
        self._validate_manifest_shape(manifest)
        self._writer.write(
            self._manifest_path,
            manifest,
            validator=self._validate_manifest_shape,
            backup_policy=self._backup_policy,
            backup_kind="preset-manifest",
        )

    def _ready_manifest(self) -> dict[str, Any]:
        self._ensure_open()
        if self._needs_recovery:
            raise RepositoryRecoveryRequired("PresetRepository 存在未恢复事务")
        manifest = self._load_manifest()
        self._validate_consistency(manifest)
        return manifest

    def _load_manifest(self) -> dict[str, Any]:
        if not self._manifest_path.exists():
            return {}
        if not self._manifest_path.is_file() or self._manifest_path.is_symlink():
            raise RepositoryRecoveryRequired("Preset manifest 路径不安全")
        manifest = self._read_json(self._manifest_path, "Preset manifest")
        self._validate_manifest_shape(manifest)
        return manifest

    def _validate_consistency(self, manifest: dict[str, Any]) -> None:
        self._validate_manifest_shape(manifest)
        if not self._root.exists():
            if manifest:
                raise RepositoryRecoveryRequired("Preset 根目录缺失")
            return
        known = set(manifest)
        for entry in self._root.iterdir():
            if entry.name in {"manifest.json", ".transactions", ".trash"}:
                continue
            if entry.name.startswith("."):
                raise RepositoryRecoveryRequired(f"Preset 根目录包含未知控制项：{entry.name}")
            if entry.is_symlink() or not entry.is_dir():
                raise RepositoryRecoveryRequired(f"Preset item 路径不安全：{entry.name}")
            self._validate_id(entry.name)
            if entry.name not in known:
                raise RepositoryRecoveryRequired(f"Preset 孤儿目录未进入 manifest：{entry.name}")
        for item_id, summary in manifest.items():
            payload = self._read_item_payload(item_id)
            if self._manifest_entry(payload) != summary:
                raise RepositoryRecoveryRequired(f"Preset manifest 与内容不一致：{item_id}")

    def _read_item_payload(self, preset_id: str) -> dict[str, Any]:
        self._validate_id(preset_id)
        item_dir = self._item_dir(preset_id)
        if item_dir.is_symlink() or not item_dir.is_dir():
            raise RepositoryRecoveryRequired(f"Preset 内容目录缺失或不安全：{preset_id}")
        path = item_dir / "preset.json"
        if not path.is_file() or path.is_symlink():
            raise RepositoryRecoveryRequired(f"Preset 内容文件缺失或不安全：{preset_id}")
        payload = self._read_json(path, f"Preset {preset_id}")
        self._validate_payload(payload, expected_id=preset_id)
        return payload

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RepositoryCorrupt(f"{label} 无法读取或 JSON 损坏") from error
        if not isinstance(value, dict):
            raise RepositoryCorrupt(f"{label} 顶层必须是对象")
        return value

    def _stage_json(self, path: Path, value: dict[str, Any], policy: BackupPolicy) -> None:
        self._writer.write(
            path,
            value,
            validator=lambda item: self._require_dict(item, "事务 JSON"),
            backup_policy=policy,
            backup_kind="transaction",
        )

    def _set_phase(
        self,
        transaction_dir: Path,
        journal: dict[str, Any],
        phase: str,
        policy: BackupPolicy,
    ) -> dict[str, Any]:
        updated = {**journal, "phase": phase}
        self._stage_json(transaction_dir / "transaction.json", updated, policy)
        return updated

    @staticmethod
    def _require_dict(value: Any, label: str) -> None:
        if not isinstance(value, dict):
            raise ValueError(f"{label} 顶层必须是对象")

    @classmethod
    def _encode(cls, preset: Preset) -> dict[str, Any]:
        payload = asdict(preset)
        cls._validate_payload(payload, expected_id=preset.id)
        return payload

    @staticmethod
    def _decode(payload: dict[str, Any]) -> Preset:
        try:
            return preset_model._from_dict(copy.deepcopy(payload))
        except (TypeError, ValueError) as error:
            raise RepositoryCorrupt("Preset Schema 无法解码") from error

    @classmethod
    def _validate_payload(cls, payload: Any, *, expected_id: str) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Preset 顶层必须是对象")
        if payload.get("schema_version") != preset_model.CURRENT_SCHEMA_VERSION:
            raise ValueError("Preset 必须是当前 Schema v2")
        if payload.get("id") != expected_id:
            raise ValueError("Preset 内容 ID 与目录不一致")
        if not isinstance(payload.get("name"), str) or not payload["name"].strip():
            raise ValueError("Preset 名称不能为空")
        preset = cls._decode(payload)
        preset_model.validate_song_query(preset.song_query)

    @classmethod
    def _validate_manifest_shape(cls, manifest: Any) -> None:
        if not isinstance(manifest, dict):
            raise ValueError("Preset manifest 顶层必须是对象")
        for item_id, summary in manifest.items():
            cls._validate_id(item_id)
            if not isinstance(summary, dict):
                raise ValueError("Preset summary 必须是对象")
            required = ("name", "layout_id", "is_default", "created_at", "updated_at")
            if any(key not in summary for key in required):
                raise ValueError("Preset summary 缺少字段")

    @staticmethod
    def _manifest_entry(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": payload["name"],
            "layout_id": payload["layout_id"],
            "is_default": payload["is_default"],
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
        }

    @staticmethod
    def _summary(preset_id: str, summary: dict[str, Any]) -> PresetSummary:
        return PresetSummary(id=preset_id, **copy.deepcopy(summary))

    @staticmethod
    def _check_revision(expected: str | None, current: str, label: str) -> None:
        if expected is not None and expected != current:
            raise RepositoryConflict(f"{label} 已被其他操作修改，请重新加载")

    @staticmethod
    def _validate_id(preset_id: str) -> None:
        if not preset_model.is_valid_preset_id(preset_id):
            raise RepositoryCorrupt(f"非法 preset_id：{preset_id!r}")

    def _item_dir(self, preset_id: str) -> Path:
        self._validate_id(preset_id)
        path = self._root / preset_id
        if path.parent != self._root:
            raise RepositoryCorrupt("Preset 路径逃逸")
        return path

    def _ensure_open(self) -> None:
        if self._closed:
            raise RepositoryClosed("PresetRepository 已关闭")

    def _merge_report(
        self,
        *,
        detected: tuple[str, ...] = (),
        recovered: tuple[str, ...] = (),
    ) -> None:
        current = self._report
        self._report = RecoveryReport(
            detected=current.detected + detected,
            recovered=current.recovered + recovered,
            quarantined=current.quarantined,
            unresolved=current.unresolved,
        )
