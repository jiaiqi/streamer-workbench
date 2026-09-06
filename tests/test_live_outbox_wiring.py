"""P0-2c：LiveService 事件经 LocalOutbox 落盘的接线测试。

写序：LiveService 变内存 → 事件入 outbox（fsync）→ state.json 原子落盘 →
drain 到 events.jsonl（按 event_id 幂等）。

覆盖：
- 正常路径：state 保存 + 事件已 drain 进 events.jsonl + outbox 清空
- drain 失败（events.append 抛错）：state 仍保存、outbox 保留，下次 drain 补发
- 崩溃窗口（outbox.append 后、repo.save 前）：事件留在 outbox，
  重启 drain 补发（与旧实现的幽灵窗口等价，文档化于 live_outbox.py）
- 不注入 outbox：行为与旧实现完全一致（回归保护）
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.live import RequestPolicy  # noqa: E402
from core.outbox import LocalOutbox  # noqa: E402
from server.ports.repositories import BackupPolicy  # noqa: E402
from server.repositories.events import FileEventStore  # noqa: E402
from server.repositories.live import FileLiveRepository  # noqa: E402
from server.services.live_persistence import LiveSessionPersistenceService  # noqa: E402
from server.services.request_policy import RequestPolicyService  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _backup(root: Path) -> BackupPolicy:
    return BackupPolicy(root / "backups", keep=3)


def _policy_factory(rv):
    return RequestPolicyService(policy=RequestPolicy(rule_version=rv))


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _read_outbox(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class LiveOutboxWiringTests(unittest.TestCase):

    def _build(self, root: Path, events_path: Path):
        repo = FileLiveRepository(root / "live-sessions", _backup(root))
        events = FileEventStore(events_path)
        outbox = LocalOutbox(root / "outbox.jsonl")
        svc = LiveSessionPersistenceService(
            live_repository=repo,
            policy_factory=_policy_factory,
            event_store=events,
            outbox=outbox,
        )
        return svc, repo, events, outbox

    def test_normal_flow_state_saved_event_drained_outbox_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)
            live = svc.create_session(rule_version="rv1", title="首播")
            svc.queue_request(live.session.id, song_id="song_1", requester_name="张三")
            # state 已保存
            snap = repo.get(live.session.id)
            self.assertIsNotNone(snap)
            self.assertEqual(len(snap.value["requests"]), 1)
            # 事件已 drain 到 events.jsonl（session_created + queue_added 等）
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("queue_added", types)
            # outbox 已清空
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_drain_failure_preserves_outbox_state_still_saved(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)
            live = svc.create_session(rule_version="rv1", title="首播")
            original_append = FileEventStore.append
            call_count = {"n": 0}

            def failing_append(self, ev):
                call_count["n"] += 1
                raise RuntimeError("events.jsonl 磁盘故障")

            with patch.object(FileEventStore, "append", failing_append):
                # create_session 的 drain 失败 → outbox 保留事件
                svc.queue_request(live.session.id, song_id="song_1",
                                  requester_name="张三")
            # state 仍然保存了（业务事实不因事件通道故障回滚）
            snap = repo.get(live.session.id)
            self.assertEqual(len(snap.value["requests"]), 1)
            # 事件保留在 outbox，等待下次启动补发
            pending = _read_outbox(root / "outbox.jsonl")
            self.assertTrue(any(e["event"]["type"] == "queue_added" for e in pending))
            self.assertEqual(_read_events(events_path), [])
            # 恢复后 drain 成功补发 + 清空
            outbox.drain(events.append)
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("queue_added", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_crash_between_outbox_append_and_save_recovers_on_next_start(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)
            live = svc.create_session(rule_version="rv1", title="首播")
            # 模拟崩溃窗口：事件已入 outbox、state 未落盘
            original_save = FileLiveRepository.save
            with patch.object(FileLiveRepository, "save",
                              lambda self, *a, **k: (_ for _ in ()).throw(
                                  RuntimeError("simulated crash"))):
                with self.assertRaises(RuntimeError):
                    svc.queue_request(live.session.id, song_id="song_1",
                                      requester_name="张三")
            # outbox 里已有事件（fsync 持久）
            pending = _read_outbox(root / "outbox.jsonl")
            self.assertTrue(any(e["event"]["type"] == "queue_added" for e in pending))
            # 重启语义：新实例 drain 补发（与 app.lifespan P0-2b 同逻辑）
            outbox.drain(events.append)
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("queue_added", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_no_outbox_injected_keeps_legacy_behavior(self):
        """不注入 outbox（旧测试/旧调用方）→ 事件直写 event_store，行为不变。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            events = FileEventStore(events_path)
            svc = LiveSessionPersistenceService(
                live_repository=repo,
                policy_factory=_policy_factory,
                event_store=events,
            )
            live = svc.create_session(rule_version="rv1", title="首播")
            svc.queue_request(live.session.id, song_id="song_1",
                              requester_name="张三")
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("queue_added", types)


if __name__ == "__main__":
    unittest.main()
