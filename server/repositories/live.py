"""R2 P3 LiveRepository——直播会话状态持久化。

存储结构 (单一文件 state.json + events.jsonl 复用):
  data/live-sessions/
    <session_id>/
      state.json                    完整 LiveSession state 快照 (含队列/权益/演出)
      backup/state-<ts>.json       N 份备份
      .trash/<session_id>          软删除目标
manifest.json                       已知 session id 列表（最小化）

state.json schema_version: 1
  session: LiveSession dict
  requests: dict[id -> SongRequest dict]
  queue: [QueueEntry dict, ...]    按 position 排序
  performances: dict[request_id -> PerformanceRecord dict]
  entitlements: dict[id -> EntitlementGrant dict]   (本会话归属的权益)
  rule_version: str
  consecutive_bumps: int
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.data.live import (
    EntitlementGrant,
    LiveSession,
    PerformanceRecord,
    QueueEntry,
    SESSION_ACTIVE,
    SongRequest,
)
from server.ports.repositories import (
    BackupPolicy,
    MISSING_REVISION,
    RecoveryReport,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    StoredSnapshot,
)
from server.repositories.atomic_json import AtomicJsonWriter


CURRENT_STATE_SCHEMA = 1


class LiveFaultInjector:
    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at

    def __call__(self, phase: str) -> None:
        if phase == self.fail_at:
            raise OSError(f"injected live crash at {phase}")


class _NullLedger:
    """无外部 ledger 时的占位：仅计数不持久。"""

    def __init__(self):
        self._count = 0

    def add(self, *_, **__):
        self._count += 1


class FileLiveRepository:
    """单 LiveSession 状态 repo。

    设计：
    - 文件: state.json, 整体为 R1a 中 PosterRepository 同样的原子写 + revision CAS
    - 复盖粒度：每次 save 替换整文件 (state 体量小, 不需 diff)
    - recovery 清理孤儿 .tmp；manifest 简化为 session_id 单列表 (R1a 中 manifest pattern)
    """

    def __init__(
        self,
        root: Path | str,
        backup_policy: BackupPolicy,
        *,
        writer: AtomicJsonWriter | None = None,
        fault_injector=None,
    ):
        self._root = Path(root).expanduser().resolve()
        self._manifest_path = self._root / "manifest.json"
        self._trash = self._root / ".trash"
        self._backup_policy = backup_policy
        self._writer = writer or AtomicJsonWriter()
        self._inject = fault_injector or LiveFaultInjector()
        self._lock = threading.RLock()
        self._closed = False
        with self._lock:
            self._ensure_root()
            self.recover()

    def _ensure_root(self) -> None:
        os.makedirs(self._root, exist_ok=True)
        if not self._manifest_path.exists():
            self._safe_write_json(self._manifest_path, {"schema_version": 1, "sessions": []})

    def _safe_write_json(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ── helpers ──

    def _session_dir(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id or session_id in (".", ".."):
            raise ValueError(f"非法 session_id：{session_id!r}")
        return self._root / session_id

    def _state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "state.json"

    def _load_manifest(self) -> dict:
        if not self._manifest_path.exists():
            return {"schema_version": 1, "sessions": []}
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryCorrupt(f"manifest 损坏：{self._manifest_path}") from exc

    def _save_manifest(self, manifest: dict) -> None:
        self._safe_write_json(self._manifest_path, manifest)

    def _add_to_manifest(self, session_id: str) -> None:
        manifest = self._load_manifest()
        ids = manifest.setdefault("sessions", [])
        if session_id not in ids:
            ids.append(session_id)
        self._save_manifest(manifest)

    def _remove_from_manifest(self, session_id: str) -> None:
        manifest = self._load_manifest()
        ids = manifest.setdefault("sessions", [])
        if session_id in ids:
            ids.remove(session_id)
        self._save_manifest(manifest)

    def _read_state(self, session_id: str) -> dict:
        path = self._state_path(session_id)
        if not path.exists():
            raise RepositoryUnavailable(f"session state 缺失：{session_id}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryCorrupt(f"state.json 损坏：{session_id}") from exc

    # ── 恢复 ──

    def recover(self) -> RecoveryReport:
        """启动清理。"""
        with self._lock:
            detected: list[str] = []
            recovered: list[str] = []
            self._ensure_root()
            for orphan in self._root.rglob("*.tmp"):
                detected.append(str(orphan))
                try:
                    orphan.unlink()
                    recovered.append(str(orphan))
                except OSError:
                    pass
            self._report = RecoveryReport(detected=tuple(detected),
                                        recovered=tuple(recovered))
            return self._report

    # ── CRUD ──

    def save(
        self,
        session_id: str,
        payload: dict,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[dict]:
        if self._closed:
            raise RepositoryClosed("LiveRepository 已关闭")
        with self._lock:
            manifest = self._load_manifest()
            cur_rev = MISSING_REVISION if session_id not in manifest.get("sessions", []) else manifest.get("revisions", {}).get(session_id, MISSING_REVISION)
            if expected_revision != cur_rev:
                raise RepositoryConflict(
                    f"live {session_id} revision 不匹配：expected={expected_revision}, current={cur_rev}"
                )
            self._ensure_root()
            self._inject("pre-write")

            def _validate(value, _sid=session_id):
                if not isinstance(value, dict):
                    raise RepositoryCorrupt("payload 必须为 dict")
                if value.get("schema_version") != CURRENT_STATE_SCHEMA:
                    raise RepositoryCorrupt(f"schema_version 必须是 {CURRENT_STATE_SCHEMA}")
                # session id 必须匹配文件名
                if value.get("session", {}).get("id") != _sid:
                    raise RepositoryCorrupt("payload.session.id 与目录名不一致")

            file_path = self._state_path(session_id)
            new_revision = self._writer.write(
                file_path,
                payload,
                validator=_validate,
                backup_policy=self._backup_policy,
                backup_kind=f"live-{session_id}",
            )
            self._inject("post-write")
            self._add_to_manifest(session_id)
            # 同时更新 manifest 内 revision
            manifest = self._load_manifest()
            manifest.setdefault("revisions", {})[session_id] = new_revision
            self._save_manifest(manifest)
            return StoredSnapshot(value=payload, revision=new_revision)

    def get(self, session_id: str) -> StoredSnapshot[dict] | None:
        if self._closed:
            raise RepositoryClosed("LiveRepository 已关闭")
        with self._lock:
            manifest = self._load_manifest()
            if session_id not in manifest.get("sessions", []):
                return None
            data = self._read_state(session_id)
            revision = manifest.get("revisions", {}).get(session_id, MISSING_REVISION)
            return StoredSnapshot(value=data, revision=revision)

    def list_sessions(self) -> StoredSnapshot[tuple[str, ...]]:
        if self._closed:
            raise RepositoryClosed("LiveRepository 已关闭")
        with self._lock:
            manifest = self._load_manifest()
            return StoredSnapshot(
                value=tuple(manifest.get("sessions", [])),
                revision="manifest",
            )

    def delete(
        self,
        session_id: str,
        *,
        expected_revision: str | None,
    ) -> bool:
        if self._closed:
            raise RepositoryClosed("LiveRepository 已关闭")
        with self._lock:
            manifest = self._load_manifest()
            current_rev = (
                MISSING_REVISION
                if session_id not in manifest.get("sessions", [])
                else manifest.get("revisions", {}).get(session_id, MISSING_REVISION)
            )
            if expected_revision != current_rev:
                raise RepositoryConflict(
                    f"live {session_id} revision 不匹配：expected={expected_revision}, current={current_rev}"
                )
            existed = session_id in manifest.get("sessions", [])
            sdir = self._session_dir(session_id)
            if sdir.exists():
                os.makedirs(self._trash, exist_ok=True)
                dst = self._trash / session_id
                i = 1
                while dst.exists():
                    dst = self._trash / f"{session_id}-{i}"
                    i += 1
                # simple rename; sdir is single dir
                import shutil
                shutil.move(str(sdir), str(dst))
            self._remove_from_manifest(session_id)
            manifest = self._load_manifest()
            manifest.get("revisions", {}).pop(session_id, None)
            self._save_manifest(manifest)
            return existed

    def close(self) -> None:
        with self._lock:
            self._closed = True
