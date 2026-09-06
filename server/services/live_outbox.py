"""P0-2c：LiveService 事件经 LocalOutbox 落盘（P0-2 outbox 的 service 层首个接入）。

写序（与 core/outbox.py 设计一致）：
1. LiveService 变内存状态
2. 事件 append 进 outbox（fsync 写穿，持久）
3. LiveSessionPersistenceService._save_state 原子写 state.json
4. drain：outbox → events.jsonl（FileEventStore.append 按 event_id 幂等），成功后清空 outbox

崩溃窗口分析（相对旧行为「事件直写 events.jsonl → 再存 state」）：
- 崩于 1/2 → 什么都没持久化，不丢不重
- 崩于 2/3 → 启动 drain 补发事件；state 缺这次变更。与旧行为的幽灵窗口等价
  （旧实现事件先落盘，同样会出现「事件在、state 旧」）
- 崩于 3/4 之间、或 drain 时 events.append 失败 → outbox 保留事件，下次启动补发。
  旧实现在这一步直接丢事件，且 events.append 抛错会把已变更的内存状态搞分叉

LiveService 只依赖鸭子类型 .append(event)，本模块对它零侵入。
"""
from __future__ import annotations

from typing import Any

from core.outbox import LocalOutbox


class OutboxEventSink:
    """LiveService 的 event_store 替身：append 进 outbox，不直写 events.jsonl。

    drain 由 LiveSessionPersistenceService._save_state 在 state 落盘成功后调用；
    进程启动时 app.lifespan 也会兜底 drain 一次（P0-2b）。
    """

    def __init__(self, outbox: LocalOutbox) -> None:
        self._outbox = outbox

    def append(self, event: dict) -> Any:
        return self._outbox.append(event)
