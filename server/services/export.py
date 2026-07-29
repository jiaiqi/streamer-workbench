"""只消费冻结输入的导出任务。"""
from __future__ import annotations

import os
import tempfile
import time
import uuid
import threading
from collections.abc import MutableMapping
from datetime import datetime
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from server.services.render_document import RenderDocument, render_document


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
class ExportJobInput:
    job_id: str
    documents: tuple[RenderDocument, ...]
    targets: tuple[ExportTarget, ...]
    event_store: Any
    job_state: dict
    cancel_event: threading.Event | None = None


def run_export_job(job_input: ExportJobInput) -> None:
    job = job_input.job_state
    started = time.perf_counter()
    try:
        for document, target in zip(job_input.documents, job_input.targets, strict=True):
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
        job_input.event_store.append({
            "schema_version": 2, "event_id": f"evt_{uuid.uuid4().hex}",
            "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": "poster_exported", "source": "export-api",
            "meta": {"job_id": job_input.job_id,
                     "document_ids": [item.document_id for item in job_input.documents],
                     "files": len(job["files"]), "total_ms": job["total_ms"]},
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
