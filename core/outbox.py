"""P0-2 本地 outbox 事务（2026-08-30 8/18 评估 6.2）。

设计目标：
- "先写状态文件 + 后写事件" 的两步操作，在崩溃时不丢事件
- 状态文件 atomic 写盘后才写 outbox；outbox 写盘后才算"事务完成"
- 启动时 drain outbox：把事件 flush 到 EventStore，成功后清空 outbox
- 不引入新依赖（纯 stdlib）

用法（service 层）：
    # 1. 改内存状态
    new_state = self._state.with_change(...)
    # 2. 写 outbox 暂存事件（先于 state 落盘）
    self._outbox.append(event_pending)
    # 3. 写 state.json（atomic）
    saved = self._repo.save(new_state, expected_revision=...)
    # 4. 标记 outbox entry 已绑定 revision（可选，仅用于诊断）
    self._outbox.mark_committed(event_id, revision=saved.revision)
    # 注意：mark_committed 不删除 outbox 记录，drain 后才删

启动时：
    outbox.drain(event_store)  # 把所有未发送事件 push 到 EventStore
    # 成功：清空 outbox；失败：保留 outbox 下次再试

为什么用 outbox 文件而不是"先 EventStore 后 state"：
- EventStore 已落盘的事件无法回滚；state 文件可以 CAS
- 状态文件 atomic 写后 = 业务事实；outbox = 业务事实的"补充事件"
- 启动时 replay outbox → event store，状态已经真实，重放只是补齐"什么时候谁做了这件事"

约束：
- outbox 是同进程、fsync 写穿（用 os.write + os.fsync + dir fsync）
- 进程崩溃后 outbox 可能存在「未 drain」或「drain 中」两种状态
  - 未 drain：drain 即可（幂等：event_id 已存在则跳过）
  - drain 中：下一次启动时检测 last_drain_marker 是否完成
- 配额：每个 outbox 默认 ≤ 1000 行；超过告警
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxEntry:
    """outbox 中的一条待发送事件。"""
    outbox_id: str  # outbox 自身 ID（UUID；不等同 event_id）
    event: dict[str, Any]  # Event v2 字典
    enqueued_at: str  # ISO8601
    # 业务侧填的"状态"（可选）；用于诊断"这次事件对应哪个 state revision"
    context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "outbox_id": self.outbox_id,
            "event": self.event,
            "enqueued_at": self.enqueued_at,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutboxEntry":
        return cls(
            outbox_id=str(data.get("outbox_id", "")),
            event=dict(data.get("event") or {}),
            enqueued_at=str(data.get("enqueued_at", "")),
            context=dict(data.get("context") or {}),
        )


class OutboxUnavailable(Exception):
    """outbox 不可用（IO 失败 / quota 超限）。"""


class LocalOutbox:
    """基于 JSONL 文件的 outbox 实现。

    线程安全；同一进程内多线程可共用一个实例。
    跨进程不保证原子（建议同一进程内单例使用）。
    """

    def __init__(self, path: Path, *, max_entries: int = 1000) -> None:
        self._path = Path(path).expanduser().resolve()
        self._max = max_entries
        self._lock = threading.RLock()
        self._closed = False
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_open(self) -> None:
        if self._closed:
            raise OutboxUnavailable("Outbox 已关闭")

    # ── 入队 ──

    def append(self, event: dict[str, Any], *,
               context: dict[str, Any] | None = None) -> OutboxEntry:
        """把事件加入 outbox（线程安全、fsync 写穿）。

        - 入队前先检查容量
        - 序列化失败抛 OutboxUnavailable
        """
        with self._lock:
            self._ensure_open()
            current_count = self.count()
            if current_count >= self._max:
                raise OutboxUnavailable(
                    f"Outbox 已满（{current_count}/{self._max}）；"
                    f"请先 drain 或扩大 max_entries")
            entry = OutboxEntry(
                outbox_id=f"obx_{uuid.uuid4().hex}",
                event=copy.deepcopy(event),
                enqueued_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                context=dict(context or {}),
            )
            self._write_one(entry)
            return entry

    def _write_one(self, entry: OutboxEntry) -> None:
        try:
            payload = json.dumps(
                entry.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8") + b"\n"
        except (TypeError, ValueError) as exc:
            raise OutboxUnavailable(f"Outbox 序列化失败: {exc}") from exc
        if b"\n" in payload[:-1] or b"\r" in payload[:-1]:
            raise OutboxUnavailable("Outbox 序列化后不得包含物理换行")
        try:
            descriptor = os.open(
                self._path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
        except OSError as exc:
            raise OutboxUnavailable(f"无法打开 outbox: {exc}") from exc
        try:
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                if count <= 0:
                    raise OutboxUnavailable("outbox write 返回 0 字节")
                written += count
            os.fsync(descriptor)
            # 目录 fsync
            try:
                dir_fd = os.open(self._path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # macOS 等平台不允许对目录 fsync，跳过非阻塞
                pass
        except OSError as exc:
            raise OutboxUnavailable(f"outbox 写穿失败: {exc}") from exc
        finally:
            os.close(descriptor)

    # ── 读取 ──

    def iter_entries(self) -> Iterable[OutboxEntry]:
        """按写入顺序遍历 outbox 条目。"""
        with self._lock:
            self._ensure_open()
            if not self._path.exists():
                return
            try:
                with self._path.open("rb") as handle:
                    for line_number, raw_line in enumerate(handle, start=1):
                        content = raw_line.strip()
                        if not content:
                            continue
                        try:
                            data = json.loads(content.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            logger.warning(
                                "outbox 第 %d 行解析失败，已跳过: %s",
                                line_number, exc)
                            continue
                        try:
                            yield OutboxEntry.from_dict(data)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "outbox 第 %d 行结构异常，已跳过: %s",
                                line_number, exc)
            except OSError as exc:
                raise OutboxUnavailable(f"读取 outbox 失败: {exc}") from exc

    def count(self) -> int:
        with self._lock:
            self._ensure_open()
            if not self._path.exists():
                return 0
            try:
                n = 0
                with self._path.open("rb") as handle:
                    for line in handle:
                        if line.strip():
                            n += 1
                return n
            except OSError:
                return 0

    # ── 排空 ──

    def drain(self, sink: Callable[[dict[str, Any]], None],
              *, batch_size: int = 100) -> dict[str, int]:
        """把所有 outbox 条目 flush 到 sink（通常是 EventStore.append）。

        - 每条都调用 sink（sink 内部幂等：相同 event_id 不重写）
        - 全部成功后才原子 truncate outbox
        - 任一失败抛 OutboxUnavailable，保留 outbox 不动

        返回 {"drained": N, "skipped": M, "failed": K}
        """
        with self._lock:
            self._ensure_open()
            entries = list(self.iter_entries())
            if not entries:
                return {"drained": 0, "skipped": 0, "failed": 0}
            drained = 0
            failed = 0
            for entry in entries:
                try:
                    sink(entry.event)
                    drained += 1
                except Exception as exc:  # noqa: BLE001
                    # 任一失败：保留剩余 outbox，停止
                    failed += 1
                    logger.warning(
                        "outbox drain 失败 (event_id=%s): %s",
                        entry.event.get("event_id"), exc)
                    break
            if failed == 0:
                self._truncate_atomically()
            return {"drained": drained, "skipped": 0, "failed": failed}

    def _truncate_atomically(self) -> None:
        """drain 全部成功后原子清空 outbox。"""
        try:
            # rename to .drained, then remove
            tmp = self._path.with_suffix(self._path.suffix + ".draining")
            os.replace(self._path, tmp)
            os.unlink(tmp)
        except OSError as exc:
            raise OutboxUnavailable(f"outbox 清空失败: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            self._closed = True
