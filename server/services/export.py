"""导出应用服务、不可变快照与只消费冻结输入的后台任务。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
import threading
from collections.abc import MutableMapping
from datetime import datetime
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from core.layouts import get_layout
from core.spec import get_canvas_spec
from server.services.render_document import RenderDocument, render_document
from server.services.render_document import build_render_document


class ExportServiceError(Exception):
    """应用服务可稳定映射到 HTTP 的基础错误。"""


class ExportThemeNotFound(ExportServiceError):
    pass


class ExportLayoutNotFound(ExportServiceError):
    pass


class ExportExecutionFailed(ExportServiceError):
    pass


class ExportJobManager(MutableMapping):
    """单 app 任务状态与线程所有者；关闭时有界等待。"""

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._threads: list[tuple[threading.Thread, threading.Event]] = []
        self._lock = threading.RLock()

    def __getitem__(self, key):
        with self._lock:
            return self._jobs[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._jobs[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._jobs[key]

    def __iter__(self):
        with self._lock:
            return iter(tuple(self._jobs))

    def __len__(self):
        with self._lock:
            return len(self._jobs)

    def start(self, job_input: "ExportJobInput") -> None:
        cancel_event = threading.Event()
        owned_input = replace(job_input, cancel_event=cancel_event)
        thread = threading.Thread(target=run_export_job, args=(owned_input,), daemon=True)
        with self._lock:
            self._threads.append((thread, cancel_event))
        thread.start()

    def close(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        with self._lock:
            workers = tuple(self._threads)
        for _, cancel_event in workers:
            cancel_event.set()
        for thread, _ in workers:
            thread.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            self._threads = [worker for worker in self._threads if worker[0].is_alive()]
            self._jobs.clear()


@dataclass(frozen=True)
class ExportTarget:
    path: Path
    theme_name: str
    page: int


@dataclass(frozen=True)
class ExportSnapshot:
    """一次导出的完整冻结事实，不持有 Repository、Request 或可变设置。"""

    snapshot_id: str
    job_id: str
    documents: tuple[RenderDocument, ...]
    targets: tuple[ExportTarget, ...]
    created_at: str

    def __post_init__(self):
        if not self.documents or len(self.documents) != len(self.targets):
            raise ValueError("导出快照必须包含等量且非空的 documents/targets")
        if any(not target.path.is_absolute() for target in self.targets):
            raise ValueError("导出目标必须是绝对路径")


@dataclass(frozen=True)
class ExportJobInput:
    snapshot: ExportSnapshot
    event_store: Any
    job_state: dict
    cancel_event: threading.Event | None = None


@dataclass(frozen=True)
class ExportSpec:
    theme: str
    page: int = 1
    canvas: str = "标准 9:16"
    avoid: bool = False
    layout: str = "grid-wrap"
    parameters: Mapping[str, int | None] | None = None


@dataclass(frozen=True)
class ExportByIdsSpec:
    """L2.2 批量按歌曲 ID 导出：每首选中歌曲渲染成 1 张 PNG 存盘。"""
    theme: str
    song_ids: tuple[str, ...]
    layout: str = "grid-wrap"
    canvas: str = "标准 9:16"
    avoid: bool = False


@dataclass(frozen=True)
class ExportByIdsFile:
    song_id: str
    title: str
    path: Path
    filename: str
    duration_ms: float | None


@dataclass(frozen=True)
class ExportByIdsResult:
    total: int
    files: tuple[ExportByIdsFile, ...]
    total_ms: float | None


@dataclass(frozen=True)
class ExportBatchSpec:
    layout: str = "grid-wrap"
    canvas: str = "抖音全屏 9:20"
    avoid: bool = True


@dataclass(frozen=True)
class ExportCompleted:
    path: Path
    filename: str
    duration_ms: float | None
    snapshot_id: str


@dataclass(frozen=True)
class ExportQueued:
    job_id: str
    total: int
    snapshot_id: str


def create_export_snapshot(*, job_id: str, documents: tuple[RenderDocument, ...],
                           targets: tuple[ExportTarget, ...],
                           created_at: str | None = None) -> ExportSnapshot:
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    identity = {
        "job_id": job_id,
        "documents": [document.document_id for document in documents],
        "targets": [{"path": str(target.path), "theme": target.theme_name,
                     "page": target.page} for target in targets],
        "created_at": created_at,
    }
    digest = hashlib.sha256(json.dumps(
        identity, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return ExportSnapshot(
        snapshot_id=f"export_{digest}", job_id=job_id,
        documents=documents, targets=targets, created_at=created_at)


class ExportApplicationService:
    """冻结 Repository 输入、创建快照并提交导出任务的唯一编排者。"""

    def __init__(self, *, song_repository, settings_repository, event_store,
                 export_job_manager: ExportJobManager, themes, font_path: Path):
        self._songs = song_repository
        self._settings = settings_repository
        self._events = event_store
        self._jobs = export_job_manager
        self._themes = themes
        self._font_path = str(font_path)

    def export_one(self, spec: ExportSpec) -> ExportCompleted:
        songs = self._songs.load()
        settings = self._settings.load()
        theme, layout, canvas, parameters = self._resolve(
            spec.theme, spec.layout, spec.canvas, spec.avoid, spec.parameters)
        filename = self._filename(theme.output_prefix, layout.id, canvas,
                                  spec.page)
        target = Path(settings.value["output_dir"]).resolve(strict=False) / filename
        document = build_render_document(
            song_snapshot=songs, theme=theme, layout_id=layout.id,
            canvas=canvas, page=spec.page, font_path=self._font_path,
            settings_revision=settings.revision, parameters=parameters)
        job_id = uuid.uuid4().hex[:8]
        snapshot = create_export_snapshot(
            job_id=job_id, documents=(document,),
            targets=(ExportTarget(target, spec.theme, spec.page),))
        state = _new_job_state(target.parent, 1)
        run_export_job(ExportJobInput(snapshot, self._events, state))
        if state["status"] != "done":
            raise ExportExecutionFailed(state.get("error") or "导出失败")
        return ExportCompleted(target, filename, state["total_ms"],
                               snapshot.snapshot_id)

    def enqueue_batch(self, spec: ExportBatchSpec) -> ExportQueued:
        songs = self._songs.load()
        settings = self._settings.load()
        try:
            layout = get_layout(spec.layout)
        except KeyError as error:
            raise ExportLayoutNotFound(str(error)) from error
        canvas = get_canvas_spec(
            spec.canvas, avoid=spec.avoid, default="抖音全屏 9:20")
        output_dir = Path(settings.value["output_dir"]).resolve(strict=False)
        pages = layout.pages or 2
        documents: list[RenderDocument] = []
        targets: list[ExportTarget] = []
        for theme_name, theme in self._themes.items():
            for page in range(1, pages + 1):
                documents.append(build_render_document(
                    song_snapshot=songs, theme=theme, layout_id=layout.id,
                    canvas=canvas, page=page, font_path=self._font_path,
                    settings_revision=settings.revision))
                filename = self._filename(theme.output_prefix, layout.id,
                                          canvas, page)
                targets.append(ExportTarget(
                    output_dir / filename, theme_name, page))
        job_id = uuid.uuid4().hex[:8]
        snapshot = create_export_snapshot(
            job_id=job_id, documents=tuple(documents), targets=tuple(targets))
        state = _new_job_state(output_dir, len(targets))
        self._jobs[job_id] = state
        self._jobs.start(ExportJobInput(snapshot, self._events, state))
        return ExportQueued(job_id, len(targets), snapshot.snapshot_id)

    def job(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def export_by_song_ids(self, spec: ExportByIdsSpec) -> ExportByIdsResult:
        """L2.2: 按 song_ids 列表，每首选中歌曲渲染成 1 张 PNG（page=1）存盘。"""
        from server.ports.repositories import StoredSnapshot  # 局部避免循环
        from core.data.songs import SongLibrary
        started = time.perf_counter()
        theme, layout, canvas, _ = self._resolve(
            spec.theme, spec.layout, spec.canvas, spec.avoid, None)
        settings = self._settings.load()
        output_dir = Path(settings.value["output_dir"]).resolve(strict=False)
        output_dir.mkdir(parents=True, exist_ok=True)
        full_snapshot = self._songs.load()
        active_by_id = {s.id: s for s in full_snapshot.value.active()}
        files: list[ExportByIdsFile] = []
        for song_id in spec.song_ids:
            song = active_by_id.get(song_id)
            if song is None:
                continue
            temp_snapshot = StoredSnapshot[SongLibrary](
                value=SongLibrary(songs=[song]), revision=full_snapshot.revision)
            document = build_render_document(
                song_snapshot=temp_snapshot, theme=theme,
                layout_id=layout.id, canvas=canvas, page=1,
                font_path=self._font_path,
                settings_revision=settings.revision,
                title=song.title)
            t0 = time.perf_counter()
            image = render_document(document)
            filename = self._filename_for_song(theme.output_prefix, layout.id, canvas, song)
            target = output_dir / filename
            _publish_png(image, target)
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            files.append(ExportByIdsFile(
                song_id=song.id, title=song.title, path=target,
                filename=filename, duration_ms=duration_ms))
        total_ms = round((time.perf_counter() - started) * 1000, 1)
        return ExportByIdsResult(
            total=len(files), files=tuple(files), total_ms=total_ms)

    def output_directory(self) -> Path:
        settings = self._settings.load()
        return Path(settings.value["output_dir"]).resolve(strict=False)

    def _resolve(self, theme_name: str, layout_id: str, canvas_name: str,
                 avoid: bool, parameters):
        theme = self._themes.get(theme_name)
        if theme is None:
            raise ExportThemeNotFound(f"未知主题：{theme_name}")
        try:
            layout = get_layout(layout_id)
        except KeyError as error:
            raise ExportLayoutNotFound(str(error)) from error
        canvas = get_canvas_spec(canvas_name, avoid=avoid)
        values = {key: value for key, value in dict(parameters or {}).items()
                  if value is not None}
        if values:
            canvas = replace(canvas, **values)
        return theme, layout, canvas, values

    @staticmethod
    def _filename(prefix: str, layout_id: str, canvas, page: int) -> str:
        tag = ("糖圆体全屏绕排"
               if canvas.avoid_zones and canvas.height > 1920 else "糖圆体")
        return f"{prefix}-{layout_id}-{tag}-{page}.png"

    @staticmethod
    def _filename_for_song(prefix: str, layout_id: str, canvas, song) -> str:
        """L2.2: 单曲文件名 `<prefix>-<layout_id>-<title_slug>-<song_id>.png`"""
        import re as _re
        tag = ("全屏" if canvas.avoid_zones and canvas.height > 1920 else "标准")
        slug = _re.sub(r"[^\w\u4e00-\u9fff]+", "-", song.title).strip("-")[:32] or "untitled"
        return f"{prefix}-{layout_id}-{tag}-{slug}-{song.id}.png"


def _new_job_state(output_dir: Path, total: int) -> dict:
    return {
        "status": "running", "done": 0, "total": total, "current": "",
        "files": [], "output_dir": str(output_dir), "total_ms": None,
        "error": None,
    }


def run_export_job(job_input: ExportJobInput) -> None:
    snapshot = job_input.snapshot
    job = job_input.job_state
    started = time.perf_counter()
    try:
        for document, target in zip(
                snapshot.documents, snapshot.targets, strict=True):
            if job_input.cancel_event and job_input.cancel_event.is_set():
                job["status"] = "cancelled"
                return
            job["current"] = f"{target.theme_name} p{target.page}"
            image = render_document(document)
            if job_input.cancel_event and job_input.cancel_event.is_set():
                job["status"] = "cancelled"
                return
            _publish_png(image, target.path)
            job["files"].append({"theme": target.theme_name, "page": target.page,
                                 "path": str(target.path)})
            job["done"] += 1
        job["status"] = "done"
        job["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        files = len(job["files"])
        themes = sorted({target.theme_name for target in snapshot.targets})
        subject = "，".join(themes) if files == 1 and themes else f"{len(themes)} 个主题 × {files // max(len(themes), 1) if themes else files} 页"
        job_input.event_store.append({
            "schema_version": 2, "event_id": f"evt_{uuid.uuid4().hex}",
            "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": "poster_exported", "source": "export-api",
            "meta": {"kind": "grid-export",
                     "job_id": snapshot.job_id,
                     "snapshot_id": snapshot.snapshot_id,
                     "document_ids": [item.document_id for item in snapshot.documents],
                     "files": files, "total_ms": job["total_ms"],
                     "subject": subject, "themes": themes,
                     "output_dir": str(snapshot.targets[0].path.parent) if snapshot.targets else ""},
        })
    except Exception as error:
        job["status"] = "error"
        job["error"] = str(error)
    finally:
        if job["total_ms"] is None:
            job["total_ms"] = round((time.perf_counter() - started) * 1000, 1)


def _publish_png(image, target: Path) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                              dir=target.parent)
    os.close(descriptor)
    try:
        image.save(temporary, "PNG")
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        try:
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
