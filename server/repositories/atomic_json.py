"""同目录临时文件、刷盘、备份和原子替换的 JSON writer。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.ports.repositories import (
    BackupPolicy,
    MISSING_REVISION,
    RepositoryCorrupt,
    RepositoryUnavailable,
)


JsonValidator = Callable[[Any], None]


class FaultInjector:
    """测试故障注入器；生产默认不注入。"""

    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at

    def __call__(self, phase: str) -> None:
        if phase == self.fail_at:
            raise OSError(f"injected failure at {phase}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def json_revision(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _fsync_directory(path: Path) -> None:
    """尽力刷盘目录项；不支持目录 fsync 的平台安全降级。"""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            # Windows、部分网络/虚拟文件系统不支持目录 fsync。
            pass
    finally:
        os.close(fd)


def _write_bytes_atomically(path: Path, content: bytes) -> None:
    """不经过故障注入写入备份或回滚副本。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_directory(path.parent)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


class AtomicJsonWriter:
    """可重用的 JSON 原子发布器；每次调用由 Repository 私有锁包围。"""

    def __init__(self, fault_injector: Callable[[str], None] | None = None):
        self._inject = fault_injector or (lambda _phase: None)

    def write(
        self,
        target: Path,
        value: Any,
        *,
        validator: JsonValidator,
        backup_policy: BackupPolicy,
        backup_kind: str,
    ) -> str:
        target = Path(target).expanduser().resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            old_exists = target.is_file()
            old_bytes = target.read_bytes() if old_exists else None
            fd, raw_temp = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
            )
        except OSError as error:
            raise RepositoryUnavailable("无法准备 JSON 原子写入") from error
        temp = Path(raw_temp)
        published = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                self._inject("before_temp_write")
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                self._inject("after_temp_write")
                self._inject("before_temp_flush")
                handle.flush()
                self._inject("before_temp_fsync")
                os.fsync(handle.fileno())
            self._inject("after_temp_fsync")

            try:
                with temp.open("r", encoding="utf-8") as handle:
                    staged = json.load(handle)
                validator(staged)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
                raise RepositoryCorrupt("临时 JSON 校验失败") from error
            self._inject("after_validate")

            if old_bytes is not None and backup_policy.enabled and backup_policy.keep > 0:
                self._inject("before_backup_write")
                self._create_backup(old_bytes, backup_policy, backup_kind)
            self._inject("after_backup")
            self._inject("before_replace")
            os.replace(temp, target)
            published = True
            self._inject("after_replace")
            self._inject("before_directory_fsync")
            _fsync_directory(target.parent)
            self._inject("after_directory_fsync")

            try:
                with target.open("r", encoding="utf-8") as handle:
                    stored = json.load(handle)
                validator(stored)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
                raise RepositoryCorrupt("发布后的 JSON 校验失败") from error
            if canonical_json_bytes(stored) != canonical_json_bytes(value):
                raise RepositoryCorrupt("发布后的 JSON 内容与待写入值不一致")
            self._inject("after_verify")
            revision = json_revision(stored)
        except BaseException as error:
            temp.unlink(missing_ok=True)
            if published:
                try:
                    if old_bytes is None:
                        target.unlink(missing_ok=True)
                        _fsync_directory(target.parent)
                    else:
                        _write_bytes_atomically(target, old_bytes)
                except BaseException as rollback_error:
                    raise RepositoryUnavailable("JSON 发布失败且旧目标恢复失败") from rollback_error
            if isinstance(error, (RepositoryCorrupt, RepositoryUnavailable)):
                raise
            raise RepositoryUnavailable("JSON 原子写入失败，旧目标已保留") from error
        else:
            temp.unlink(missing_ok=True)
            self._trim_backups(backup_policy, backup_kind)
            return revision

    def _create_backup(self, content: bytes, policy: BackupPolicy, kind: str) -> Path:
        root = policy.root
        root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        path = root / f"{kind}-{timestamp}-{uuid.uuid4().hex[:8]}.json"
        _write_bytes_atomically(path, content)
        if path.read_bytes() != content:
            raise RepositoryUnavailable("写前备份校验失败")
        return path

    @staticmethod
    def _trim_backups(policy: BackupPolicy, kind: str) -> None:
        if not policy.enabled or policy.keep <= 0 or not policy.root.is_dir():
            return
        try:
            backups = sorted(
                policy.root.glob(f"{kind}-*.json"),
                key=lambda path: (path.stat().st_mtime_ns, path.name),
                reverse=True,
            )
            for old in backups[policy.keep:]:
                old.unlink()
        except OSError:
            # 新目标已提交成功；保留清理失败不得反向破坏提交。
            return
