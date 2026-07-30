"""用户数据目录契约（R0.9）：查询、验证、切换与迁移。

守护规则：
- 验证失败不切换、不丢数据——所有检查通过后才原子写入启动配置；
- 旧目录内容在任何路径下都不被修改或删除，迁移只做复制；
- 启动配置（startup.json）独立于数据目录，避免 settings.json 自我定位；
- 服务可在无 UI 场景使用，Electron/设置页都只是调用方。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from server.config import (
    AppConfig,
    AppPaths,
    DataRootSource,
    _absolute,
    platform_data_root,
    resolve_data_root_source,
)
from server.ports.repositories import BackupPolicy, RepositoryError
from server.repositories.atomic_json import AtomicJsonWriter

STANDARD_SUBDIRS = ("tabs", "presets", "layouts", "backups", "output")
DATA_FILES = ("songs.json", "events.jsonl", "settings.json")
DATA_DIRS = ("tabs", "presets", "layouts", "output")
STARTUP_SCHEMA_VERSION = 1

SOURCE_LABELS: dict[DataRootSource, str] = {
    "explicit": "启动参数",
    "environment": "环境变量",
    "startup": "启动配置",
    "development": "开发默认",
    "platform": "平台默认",
}


class DataDirError(Exception):
    """数据目录用例的稳定业务错误基类。"""


class DataDirValidationFailed(DataDirError):
    """候选目录不满足约束；对应 HTTP 400。"""


class DataDirConflict(DataDirError):
    """目标目录已有数据且调用方未声明处理方式；对应 HTTP 409。"""

    def __init__(self, message: str, *, existing_items: list[str]):
        super().__init__(message)
        self.existing_items = existing_items


class DataDirUnavailable(DataDirError):
    """文件系统操作失败；对应 HTTP 503。"""


@dataclass(frozen=True)
class DataDirInspection:
    """候选目录的只读体检结果；inspect 不产生任何写入。"""

    path: Path
    valid: bool
    message: str = ""
    exists: bool = False
    is_current: bool = False
    parent_writable: bool = False
    has_existing_data: bool = False
    existing_items: list[str] = field(default_factory=list)

    @property
    def will_initialize(self) -> bool:
        return self.valid and not self.has_existing_data


def _normalize_candidate(raw: str) -> Path:
    text = (raw or "").strip()
    if not text:
        raise DataDirValidationFailed("目录路径不能为空")
    expanded = Path(text).expanduser()
    if not expanded.is_absolute():
        raise DataDirValidationFailed(f"目录必须是绝对路径：{text}")
    return _absolute(expanded)


def _nearest_existing_ancestor(path: Path) -> Path | None:
    candidate = path
    while True:
        if candidate.exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent


def _existing_data_items(root: Path) -> list[str]:
    """列出目录内已存在的用户数据痕迹；目录不存在时为空。"""
    items: list[str] = []
    if not root.is_dir():
        return items
    for name in DATA_FILES:
        if (root / name).is_file():
            items.append(name)
    for name in DATA_DIRS:
        folder = root / name
        if folder.is_dir() and any(folder.rglob("*")):
            items.append(f"{name}/")
    return items


class DataDirectoryService:
    """数据目录状态查询、候选验证与切换；写入只发生在 startup.json。"""

    def __init__(self, *, config: AppConfig, paths: AppPaths,
                 environ: Mapping[str, str] | None = None):
        self._config = config
        self._paths = paths
        self._environ = environ if environ is not None else os.environ

    # ---- 查询 ----

    def status(self) -> dict[str, Any]:
        data_root, startup_path, source = resolve_data_root_source(
            self._config, environ=self._environ)
        try:
            platform_default: str | None = str(
                platform_data_root(environ=self._environ))
        except ValueError:
            platform_default = None
        return {
            "current": str(data_root),
            "source": source,
            "source_label": SOURCE_LABELS[source],
            "startup_config": str(startup_path),
            "platform_default": platform_default,
            "pinned": source in ("explicit", "environment"),
        }

    # ---- 只读验证 ----

    def inspect(self, candidate: str) -> DataDirInspection:
        try:
            target = _normalize_candidate(candidate)
        except DataDirValidationFailed as error:
            return DataDirInspection(
                path=Path(candidate or "."), valid=False, message=str(error))
        current = self._paths.data_root
        if target == current:
            return DataDirInspection(
                path=target, valid=False, is_current=True,
                message="该目录就是当前数据目录")
        containment = self._containment_error(target)
        if containment:
            return DataDirInspection(
                path=target, valid=False, message=containment)
        if target.exists() and not target.is_dir():
            return DataDirInspection(
                path=target, valid=False, exists=True,
                message="目标已存在且不是目录")
        ancestor = _nearest_existing_ancestor(target)
        parent_writable = bool(
            ancestor is not None and os.access(ancestor, os.W_OK | os.X_OK))
        items = _existing_data_items(target)
        message = ""
        if not parent_writable:
            message = "没有该目录的写入权限"
        return DataDirInspection(
            path=target,
            valid=parent_writable,
            message=message,
            exists=target.exists(),
            parent_writable=parent_writable,
            has_existing_data=bool(items),
            existing_items=items,
        )

    # ---- 切换 ----

    def switch(self, candidate: str, *, migrate: bool = False,
               use_existing: bool = False) -> dict[str, Any]:
        inspection = self.inspect(candidate)
        if not inspection.valid:
            raise DataDirValidationFailed(
                inspection.message or "目录验证失败")
        target = inspection.path
        if inspection.has_existing_data and not use_existing and not migrate:
            raise DataDirConflict(
                "目标目录已有数据，需确认使用已有数据或选择其他目录",
                existing_items=inspection.existing_items)
        if migrate and inspection.has_existing_data:
            raise DataDirConflict(
                "目标目录已有数据，无法安全迁移；请改用已有数据或换空目录",
                existing_items=inspection.existing_items)

        self._prepare_target(target)
        migrated = self._migrate_current_data(target) if migrate else []
        self._initialize_structure(target)
        self._publish_startup_config(target)
        return {
            "ok": True,
            "data_root": str(target),
            "startup_config": str(self._paths.startup_config_path),
            "requires_restart": True,
            "migrated": migrated,
            "used_existing": bool(inspection.has_existing_data and use_existing),
        }

    # ---- 内部 ----

    def _containment_error(self, target: Path) -> str:
        current = self._paths.data_root
        if target == current:
            return "该目录就是当前数据目录"
        if target.is_relative_to(current):
            return "新目录不能位于当前数据目录内部"
        if current.is_relative_to(target):
            return "新目录不能是当前数据目录的父目录"
        return ""

    def _prepare_target(self, target: Path) -> None:
        """创建目标目录并做写入探针；失败在任何数据复制之前抛出。"""
        try:
            target.mkdir(parents=True, exist_ok=True)
            fd, probe = tempfile.mkstemp(prefix=".probe-", dir=target)
            os.close(fd)
            Path(probe).unlink()
        except OSError as error:
            raise DataDirUnavailable(f"目标目录不可写：{error}") from error

    def _initialize_structure(self, target: Path) -> None:
        try:
            for name in STANDARD_SUBDIRS:
                (target / name).mkdir(exist_ok=True)
        except OSError as error:
            raise DataDirUnavailable(f"无法初始化数据目录：{error}") from error

    def _migrate_current_data(self, target: Path) -> list[str]:
        """把当前数据复制到新目录；任何冲突或失败都不写启动配置。

        调用前已保证目标没有用户数据，因此 DATA_DIRS 目标最多是空目录；
        文件级冲突逐一预检，复制失败尽力清理半成品，旧目录始终不动。
        """
        current = self._paths.data_root
        planned: list[tuple[Path, Path]] = []
        for name in DATA_FILES + DATA_DIRS:
            source = current / name
            if source.exists():
                planned.append((source, target / name))
        conflicts = [dest.name for src, dest in planned
                     if src.is_file() and dest.exists()]
        if conflicts:
            raise DataDirConflict(
                "迁移目标已存在同名数据： " + ", ".join(conflicts),
                existing_items=conflicts)
        copied: list[Path] = []
        try:
            for source, dest in planned:
                if source.is_dir():
                    shutil.copytree(source, dest, dirs_exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                copied.append(dest)
        except OSError as error:
            for dest in reversed(copied):
                try:
                    if dest.is_dir():
                        shutil.rmtree(dest, ignore_errors=True)
                    else:
                        dest.unlink(missing_ok=True)
                except OSError:
                    pass
            raise DataDirUnavailable(f"迁移数据失败，旧目录未受影响：{error}") from error
        return [dest.name for dest in copied]

    def _publish_startup_config(self, target: Path) -> None:
        payload = {
            "schemaVersion": STARTUP_SCHEMA_VERSION,
            "data_root": str(target),
        }

        def validator(value: Any) -> None:
            if (not isinstance(value, dict)
                    or value.get("schemaVersion") != STARTUP_SCHEMA_VERSION
                    or not isinstance(value.get("data_root"), str)
                    or not value["data_root"]):
                raise ValueError("启动配置内容不合法")

        startup_path = self._paths.startup_config_path
        policy = BackupPolicy(startup_path.parent / "backups", keep=5)
        try:
            AtomicJsonWriter().write(
                startup_path, payload,
                validator=validator,
                backup_policy=policy,
                backup_kind="startup",
            )
        except RepositoryError as error:
            raise DataDirUnavailable(f"写入启动配置失败：{error}") from error
