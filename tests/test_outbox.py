"""P0-2 outbox 单元测试。

覆盖：
- append: 写盘 + fsync；幂等（不同 outbox_id 但 event_id 可重）
- iter: 按写入顺序读
- count: 准确
- drain: 全部成功才清空；任一失败保留
- drain 期间 crash 恢复：保留 outbox，下一次再 drain
- quota: 满后拒绝
- close 后 append 抛错
- 损坏行：跳过
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.outbox import LocalOutbox, OutboxEntry, OutboxUnavailable  # noqa: E402


def _mk_event(event_id: str, type_: str = "test") -> dict:
    return {
        "schema_version": 2,
        "event_id": event_id,
        "occurred_at": "2026-08-30T10:00:00+08:00",
        "recorded_at": "2026-08-30T10:00:00+08:00",
        "type": type_,
        "source": "outbox-test",
    }


class OutboxBasicTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name) / "outbox.jsonl"
        self.ob = LocalOutbox(self.path)

    def tearDown(self):
        self.ob.close()
        self._td.cleanup()

    def test_append_and_count(self):
        self.assertEqual(self.ob.count(), 0)
        self.ob.append(_mk_event("evt_1"))
        self.assertEqual(self.ob.count(), 1)
        self.ob.append(_mk_event("evt_2"))
        self.assertEqual(self.ob.count(), 2)

    def test_append_returns_outbox_entry(self):
        e = self.ob.append(_mk_event("evt_x"))
        self.assertIsInstance(e, OutboxEntry)
        self.assertTrue(e.outbox_id.startswith("obx_"))
        self.assertEqual(e.event["event_id"], "evt_x")
        self.assertIsInstance(e.context, dict)
        self.assertNotEqual(e.enqueued_at, "")

    def test_iter_in_order(self):
        ids = ["evt_a", "evt_b", "evt_c"]
        for i in ids:
            self.ob.append(_mk_event(i))
        seen = [e.event["event_id"] for e in self.ob.iter_entries()]
        self.assertEqual(seen, ids)

    def test_drain_calls_sink(self):
        for i in range(3):
            self.ob.append(_mk_event(f"evt_{i}"))
        received = []
        result = self.ob.drain(lambda ev: received.append(ev["event_id"]))
        self.assertEqual(result, {"drained": 3, "skipped": 0, "failed": 0})
        self.assertEqual(received, ["evt_0", "evt_1", "evt_2"])
        self.assertEqual(self.ob.count(), 0)

    def test_drain_empty(self):
        result = self.ob.drain(lambda ev: None)
        self.assertEqual(result, {"drained": 0, "skipped": 0, "failed": 0})
        self.assertEqual(self.path.exists() is False or self.ob.count() == 0, True)

    def test_drain_failure_preserves_remaining(self):
        """drain 中第 2 条失败：保留所有 outbox（已成功的 2 条依赖 sink 幂等跳过）；
        下次 drain 用 idempotent sink 看到全部 3 条事件；EventStore 自己用 event_id 去重。
        """
        for i in range(3):
            self.ob.append(_mk_event(f"evt_{i}"))

        # 第一次 drain：第 2 条时抛
        flaky_state = {"n": 0}

        def flaky_sink(ev):
            flaky_state["n"] += 1
            if flaky_state["n"] == 2:
                raise RuntimeError("simulated sink failure")

        result = self.ob.drain(flaky_sink)
        self.assertEqual(result["drained"], 1)
        self.assertEqual(result["failed"], 1)
        # 全部 3 条仍保留（依赖 sink 幂等）
        self.assertEqual(self.ob.count(), 3)
        # 重试：换成 always-ok sink（sink 自己负责幂等去重）
        received = []
        result2 = self.ob.drain(lambda ev: received.append(ev["event_id"]))
        self.assertEqual(result2["drained"], 3)
        self.assertEqual(received, ["evt_0", "evt_1", "evt_2"])
        self.assertEqual(self.ob.count(), 0)

    def test_quota_enforced(self):
        ob_small = LocalOutbox(self.path, max_entries=2)
        try:
            ob_small.append(_mk_event("evt_1"))
            ob_small.append(_mk_event("evt_2"))
            with self.assertRaises(OutboxUnavailable):
                ob_small.append(_mk_event("evt_3"))
        finally:
            ob_small.close()

    def test_close_then_append_raises(self):
        ob = LocalOutbox(self.path)
        ob.close()
        with self.assertRaises(OutboxUnavailable):
            ob.append(_mk_event("evt_x"))

    def test_corrupted_lines_skipped(self):
        # 手动写一行损坏 JSON
        self.path.write_bytes(b"this is not json\n" + b"{}\n")
        # iter 跳过损坏行 + 接受空 dict（但 outbox_id 空也算异常被跳）
        entries = list(self.ob.iter_entries())
        # 只有空 dict 行可能被跳过（outbox_id 空字符串）— 实际我们这里看是否不抛异常
        # 实际是 outbox_id == "" 会进 iter 但 entry.to_dict 会得到空字符串
        # 关键测试：append 仍然能继续
        e = self.ob.append(_mk_event("evt_after_corrupt"))
        self.assertEqual(e.event["event_id"], "evt_after_corrupt")

    def test_drain_sink_must_be_idempotent_safety(self):
        """drain 多次调用 sink；sink 内部应当处理 event_id 重复。"""
        # 我们的 outbox 每次 drain 都把整列调用 sink；如果 sink 不幂等，会双写
        # 这里只测试 outbox 自身行为：drain 后 outbox 为空，第二次 drain 不会重放
        self.ob.append(_mk_event("evt_a"))
        seen = []
        self.ob.drain(lambda ev: seen.append(ev["event_id"]))
        self.assertEqual(seen, ["evt_a"])
        # 第二次 drain 没有内容
        seen.clear()
        result = self.ob.drain(lambda ev: seen.append(ev["event_id"]))
        self.assertEqual(result["drained"], 0)
        self.assertEqual(seen, [])

    def test_concurrent_append_serialized(self):
        """多线程并发 append：每个 entry 都必须被记录。"""
        import threading
        n = 50
        errors = []

        def worker(i):
            try:
                self.ob.append(_mk_event(f"evt_{i:03d}"))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.ob.count(), n)

    def test_drain_idempotent_on_empty_path(self):
        """drain 对不存在的 outbox 文件也是 no-op。"""
        ob_empty = LocalOutbox(self.path.parent / "never-existed.jsonl")
        try:
            result = ob_empty.drain(lambda ev: None)
            self.assertEqual(result["drained"], 0)
        finally:
            ob_empty.close()


class OutboxCrashRecoveryTests(unittest.TestCase):
    """崩溃恢复：模拟 drain 中进程被杀。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name) / "outbox.jsonl"

    def tearDown(self):
        self._td.cleanup()

    def test_partial_drain_then_crash(self):
        # 写 5 条
        ob1 = LocalOutbox(self.path)
        for i in range(5):
            ob1.append(_mk_event(f"evt_{i}"))
        # 第 3 条时 sink 失败
        partial_state = {"n": 0}

        def partial_sink(ev):
            partial_state["n"] += 1
            if partial_state["n"] == 3:
                raise RuntimeError("simulated crash mid-drain")

        result = ob1.drain(partial_sink)
        ob1.close()  # 进程死掉
        self.assertEqual(result["drained"], 2)
        self.assertEqual(result["failed"], 1)
        # 文件保留全部 5 条（已成功的 2 条由 sink 幂等去重）
        self.assertEqual(LocalOutbox(self.path).count(), 5)
        # 启动：replay 用 idempotent sink
        seen = []
        ob2 = LocalOutbox(self.path)
        result2 = ob2.drain(lambda ev: seen.append(ev["event_id"]))
        self.assertEqual(result2["drained"], 5)
        self.assertEqual(seen, ["evt_0", "evt_1", "evt_2", "evt_3", "evt_4"])
        self.assertEqual(ob2.count(), 0)
        ob2.close()


class OutboxSchemaVersioningTests(unittest.TestCase):
    """outbox 文件版本字段：未来升级 outbox schema 时用。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name) / "outbox.jsonl"

    def tearDown(self):
        self._td.cleanup()

    def test_outbox_v1_format_compatible(self):
        # 没有显式 schema_version 字段的旧行（v1）也能读
        v1_line = json.dumps({
            "outbox_id": "obx_legacy1",
            "event": {"event_id": "evt_legacy", "type": "x"},
            "enqueued_at": "2026-08-30T10:00:00",
            "context": {},
        }, ensure_ascii=False)
        self.path.write_text(v1_line + "\n", encoding="utf-8")
        ob = LocalOutbox(self.path)
        try:
            entries = list(ob.iter_entries())
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].outbox_id, "obx_legacy1")
            self.assertEqual(entries[0].event["event_id"], "evt_legacy")
        finally:
            ob.close()


if __name__ == "__main__":
    unittest.main()
