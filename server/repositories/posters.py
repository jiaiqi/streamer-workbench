"""R1a.1 FilePosterRepository adapter——原子写 + 备份 + revision CAS + 启动恢复。

设计要点：
- 与 FilePresetRepository 共享 AtomicJsonWriter；revision = content sha256；
- 软删除使用 .trash 子目录（与 Preset 一致）；
- 只暴露 P1 必需接口（list/get/save/delete/recover/close）；
- expected_revision 校验失败抛 RepositoryConflict，写入原子保留旧值；
- 启动时扫描 .transactions 和孤儿 .tmp/.bak；recover() 返回 RecoveryReport。
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from core.data.posters import PosterDocument, is_valid_poster_id
from server.ports.repositories import (
    BackupPolicy,
    MISSING_REVISION,
    PosterRepository,
    PosterSummary,
    RecoveryReport,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
    StoredSnapshot,
)
from server.repositories.atomic_json import AtomicJsonWriter


class PosterFaultInjector:
    """测试用故障注入器；生产默认不注入。"""

    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at

    def __call__(self, phase: str) -> None:
        if phase == self.fail_at:
            raise OSError(f"injected poster crash at {phase}")


class FilePosterRepository(PosterRepository):
    """manifest + per-poster file 全包提交、实例私有锁和启动恢复。"""

    def __init__(
        self,
        root: Path | str,
        backup_policy: BackupPolicy,
        *,
        writer: AtomicJsonWriter | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ):
        self._root = Path(root).expanduser().resolve()
        self._manifest_path = self._root / "manifest.json"
        self._trash = self._root / ".trash"
        self._backup_policy = backup_policy
        self._writer = writer or AtomicJsonWriter()
        self._inject = fault_injector or (lambda _phase: None)
        self._lock = threading.RLock()
        self._closed = False
        self._needs_recovery = False
        self._report = RecoveryReport()
        with self._lock:
            self._ensure_root()
            self.recover()

    # ── 私有 ──

    def _ensure_root(self) -> None:
        os.makedirs(self._root, exist_ok=True)
        if not self._manifest_path.exists():
            self._safe_write_json(self._manifest_path, {})

    def _safe_write_json(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _load_manifest(self) -> dict:
        if not self._manifest_path.exists():
            return {}
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryCorrupt(f"manifest 损坏：{self._manifest_path}") from exc

    def _save_manifest(self, manifest: dict) -> None:
        self._safe_write_json(self._manifest_path, manifest)

    def _poster_dir(self, poster_id: str) -> Path:
        if not is_valid_poster_id(poster_id):
            raise ValueError(f"非法 poster_id：{poster_id!r}")
        return self._root / poster_id

    def _backup_existing(self, file_path: Path) -> None:
        if not file_path.exists() or not self._backup_policy.enabled:
            return
        backup_dir = self._backup_policy.root / file_path.parent.name
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = backup_dir / f"{file_path.stem}_{ts}.json"
        shutil.copy2(file_path, backup_path)
        # 清理旧备份
        backups = sorted(
            (backup_dir.glob(f"{file_path.stem}_*.json")),
            key=lambda p: p.stat().st_mtime,
        )
        for old in backups[:-self._backup_policy.keep]:
            try:
                old.unlink()
            except OSError:
                pass

    def _summary(self, poster_id: str, info: dict) -> PosterSummary:
        return PosterSummary(
            id=poster_id,
            name=info.get("name", ""),
            layout_id=info.get("layout_id", "grid-wrap"),
            theme_id=info.get("theme_id", ""),
            canvas_id=info.get("canvas_id", ""),
            created_at=info.get("created_at", ""),
            updated_at=info.get("updated_at", ""),
            song_count=int(info.get("song_count", 0)),
            # M3 P2: 从 manifest entry 读 order_index（None 表示未排序）
            order_index=(int(info["order_index"])
                         if isinstance(info.get("order_index"), int)
                         else None),
        )

    def _read_poster_file(self, poster_id: str) -> PosterDocument:
        path = self._poster_dir(poster_id) / "poster.json"
        if not path.exists():
            raise RepositoryUnavailable(f"poster 文件缺失：{poster_id}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryCorrupt(f"poster.json 损坏：{poster_id}") from exc
        return PosterDocument.from_dict(data)

    def _refresh_summary_in_manifest(self, poster_id: str, doc: PosterDocument) -> dict:
        manifest = self._load_manifest()
        manifest[poster_id] = {
            "name": doc.name,
            "layout_id": doc.layout_id,
            "theme_id": doc.theme_id,
            "canvas_id": doc.canvas_id,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
            "song_count": len(doc.selected_song_ids),
            # M3 P2: order_index 持久化到 manifest 便于 list 排序；None 时不写 key
            **({"order_index": int(doc.order_index)} if doc.order_index is not None else {}),
        }
        return manifest

    # ── Port 实现 ──

    def list(self) -> StoredSnapshot[tuple[PosterSummary, ...]]:
        if self._closed:
            raise RepositoryClosed("PosterRepository 已关闭")
        with self._lock:
            manifest = self._load_manifest()
            summaries = []
            for pid in manifest:
                summaries.append(self._summary(pid, manifest[pid]))
            # M3 P2 排序（多轮 stable sort 累积）：
            # 1) id desc（最新 sort 的 key 优先；前次顺序在组内保留）
            # 2) order_index 升序（None 用 10^12 推到末尾段）
            # 3) updated_at desc
            # 设计权衡：依赖 Python sort 稳定特性，比 cmp_to_key 简单
            summaries.sort(key=lambda s: s.id, reverse=True)
            summaries.sort(key=lambda s: (
                s.order_index if s.order_index is not None else 10**12,
            ))
            summaries.sort(key=lambda s: s.updated_at, reverse=True)
            return StoredSnapshot(value=tuple(summaries), revision="manifest")

    def get(self, poster_id: str) -> StoredSnapshot[PosterDocument] | None:
        if self._closed:
            raise RepositoryClosed("PosterRepository 已关闭")
        if not is_valid_poster_id(poster_id):
            return None
        with self._lock:
            manifest = self._load_manifest()
            if poster_id not in manifest:
                return None
            doc = self._read_poster_file(poster_id)
            revision = manifest[poster_id].get("revision") or MISSING_REVISION
            return StoredSnapshot(value=doc, revision=revision)

    def save(
        self,
        poster: PosterDocument,
        *,
        expected_revision: str | None,
    ) -> StoredSnapshot[PosterDocument]:
        if self._closed:
            raise RepositoryClosed("PosterRepository 已关闭")
        poster.validate()  # 校验收紧：拒绝带病写入
        with self._lock:
            manifest = self._load_manifest()
            current_rev = MISSING_REVISION if poster.id not in manifest else manifest[poster.id].get("revision", MISSING_REVISION)
            if expected_revision != current_rev:
                raise RepositoryConflict(
                    f"poster {poster.id} revision 不匹配：expected={expected_revision}, current={current_rev}"
                )
            self._inject("pre-write")
            file_path = self._poster_dir(poster.id) / "poster.json"
            def _validate_poster_payload(value, expected_id=poster.id):
                if not isinstance(value, dict):
                    raise RepositoryCorrupt("poster payload 必须为 dict")
                if value.get("id") != expected_id:
                    raise RepositoryCorrupt("poster payload id 不匹配")
                # 完整 schema 校验——再次防御性约束
                PosterDocument.from_dict(value).validate()
            new_revision = self._writer.write(
                file_path,
                poster.to_dict(),
                validator=_validate_poster_payload,
                backup_policy=self._backup_policy,
                backup_kind=f"poster-{poster.id}",
            )
            self._inject("post-write")
            # 更新 manifest（同步包含 revision 便于列表 CAS）
            new_manifest = self._refresh_summary_in_manifest(poster.id, poster)
            new_manifest[poster.id]["revision"] = new_revision
            self._save_manifest(new_manifest)
            return StoredSnapshot(value=poster, revision=new_revision)

    def delete(self, poster_id: str, *, expected_revision: str | None) -> bool:
        if self._closed:
            raise RepositoryClosed("PosterRepository 已关闭")
        if not is_valid_poster_id(poster_id):
            return False
        with self._lock:
            manifest = self._load_manifest()
            current_rev = MISSING_REVISION if poster_id not in manifest else manifest[poster_id].get("revision", MISSING_REVISION)
            if expected_revision != current_rev:
                raise RepositoryConflict(
                    f"poster {poster_id} revision 不匹配：expected={expected_revision}, current={current_rev}"
                )
            existed = poster_id in manifest or self._poster_dir(poster_id).exists()
            if self._poster_dir(poster_id).exists():
                os.makedirs(self._trash, exist_ok=True)
                dst = self._trash / poster_id
                i = 1
                while dst.exists():
                    dst = self._trash / f"{poster_id}-{i}"
                    i += 1
                shutil.move(str(self._poster_dir(poster_id)), str(dst))
            manifest.pop(poster_id, None)
            self._save_manifest(manifest)
            return existed

    def recover(self) -> RecoveryReport:
        """启动恢复：清理孤儿 .tmp/.bak，重建空 manifest。"""
        with self._lock:
            detected: list[str] = []
            recovered: list[str] = []
            quarantined: list[str] = []
            # 清理 .trash 中非常老的项目（可选；P1 不做）
            # 检测/恢复 .tmp 临时文件
            for entry in self._root.rglob("*.tmp"):
                detected.append(str(entry))
                try:
                    entry.unlink()
                    recovered.append(str(entry))
                except OSError:
                    quarantined.append(str(entry))
            # 确保 manifest 存在
            self._ensure_root()
            self._report = RecoveryReport(
                detected=tuple(detected),
                recovered=tuple(recovered),
                quarantined=tuple(quarantined),
            )
            self._needs_recovery = False
            return self._report

    def close(self) -> None:
        with self._lock:
            self._closed = True
