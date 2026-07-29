"""R0.7 FileEventStore 独立可靠性测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.ports.repositories import (
    EventQuery,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
)
from server.repositories.events import EventFaultInjector, FileEventStore


def event(
    event_id: str,
    *,
    event_type: str = "queue_added",
    occurred_at: str = "2026-07-29T10:00:00+08:00",
    recorded_at: str = "2026-07-29T10:00:01+08:00",
    title: str = "知足",
) -> dict:
    return {
        "schema_version": 2,
        "event_id": event_id,
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
        "type": event_type,
        "source": "event-store-test",
        "song_id": "song_227fe9c4775f51e2a3e414bc78fdf12e",
        "title_snapshot": title,
        "meta": {"order": 1},
    }


def append_raw(path: Path, value: dict, *, newline: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with path.open("ab") as handle:
        handle.write(content + (b"\n" if newline else b""))
        handle.flush()
        os.fsync(handle.fileno())


class FileEventStoreTests(unittest.TestCase):
    def test_empty_and_mixed_v1_v2_startup_index_and_queries(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "events.jsonl"
            store = FileEventStore(path)
            self.assertEqual(store.index_size, 0)
            self.assertEqual(tuple(store.iter(EventQuery())), ())

            append_raw(path, {"type": "queue_added", "title": "旧事件", "ts": "2025-01-01T00:00:00"})
            append_raw(path, event("evt_a"))
            append_raw(path, event("evt_b", event_type="song_sung", occurred_at="2026-07-29T11:00:00+08:00"))

            self.assertEqual(store.get_by_id("evt_a")["title_snapshot"], "知足")
            self.assertIsNone(store.get_by_id("missing"))
            self.assertEqual(store.index_size, 2)
            self.assertEqual(len(tuple(store.iter(EventQuery()))), 3)
            self.assertEqual(
                [item["event_id"] for item in store.iter(EventQuery(event_type="song_sung"))],
                ["evt_b"],
            )
            self.assertEqual(store.tail(limit=1)[0]["event_id"], "evt_b")

    def test_idempotent_append_ignores_recorded_at_and_conflict_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "events.jsonl"
            store = FileEventStore(path)
            first = event("evt_same")
            result = store.append(first)
            self.assertEqual(result.status, "appended")
            original_size = path.stat().st_size

            replay = {**first, "recorded_at": "2030-01-01T00:00:00+08:00"}
            duplicate = store.append(replay)
            self.assertEqual(duplicate.status, "already_exists")
            self.assertEqual(duplicate.event["recorded_at"], first["recorded_at"])
            self.assertEqual(path.stat().st_size, original_size)

            with self.assertRaises(RepositoryConflict):
                store.append({**first, "title_snapshot": "冲突内容"})
            self.assertEqual(path.stat().st_size, original_size)

    def test_concurrent_same_id_appends_once_and_different_ids_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "events.jsonl"
            store = FileEventStore(path)
            barrier = threading.Barrier(5)
            statuses: list[str] = []
            status_lock = threading.Lock()

            def same_worker() -> None:
                barrier.wait()
                result = store.append(event("evt_shared"))
                with status_lock:
                    statuses.append(result.status)

            threads = [threading.Thread(target=same_worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(statuses.count("appended"), 1)
            self.assertEqual(statuses.count("already_exists"), 3)

            different = [threading.Thread(target=lambda value=value: store.append(event(value)))
                         for value in ("evt_1", "evt_2", "evt_3", "evt_4")]
            for thread in different:
                thread.start()
            for thread in different:
                thread.join(timeout=5)
            self.assertEqual(store.index_size, 5)
            self.assertEqual(len(path.read_bytes().splitlines()), 5)

    def test_truncated_tail_is_quarantined_and_complete_tail_gets_newline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            truncated_path = root / "truncated.jsonl"
            append_raw(truncated_path, event("evt_good"))
            with truncated_path.open("ab") as handle:
                handle.write(b'{"schema_version":2,"event_id":"evt_half"')
            store = FileEventStore(truncated_path)
            self.assertEqual(store.index_size, 1)
            self.assertTrue(truncated_path.read_bytes().endswith(b"\n"))
            self.assertIn("truncated_tail", store.recovery_report.detected)
            quarantine = root / f".{truncated_path.name}.recovery" / store.recovery_report.quarantined[0]
            self.assertIn(b"evt_half", quarantine.read_bytes())

            complete_path = root / "complete.jsonl"
            append_raw(complete_path, event("evt_complete"), newline=False)
            complete_store = FileEventStore(complete_path)
            self.assertEqual(complete_store.index_size, 1)
            self.assertTrue(complete_path.read_bytes().endswith(b"\n"))
            self.assertIn("appended_missing_newline", complete_store.recovery_report.recovered)

    def test_middle_corruption_invalid_utf8_invalid_v2_and_conflicting_id_block_startup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            cases: list[tuple[str, bytes]] = []
            good = json.dumps(event("evt_good"), ensure_ascii=False).encode("utf-8") + b"\n"
            cases.append(("bad-json", good + b"{bad json}\n" + good))
            cases.append(("bad-utf8", good + b"\xff\xfe\n" + good))
            invalid = {**event("evt_invalid"), "source": ""}
            cases.append(("invalid-v2", good + json.dumps(invalid).encode("utf-8") + b"\n"))
            cases.append(("invalid-v2-tail", json.dumps(invalid).encode("utf-8")))
            conflict = json.dumps({**event("evt_good"), "title_snapshot": "另一个标题"}).encode("utf-8")
            cases.append(("conflict-id", good + conflict + b"\n"))

            for name, content in cases:
                with self.subTest(name=name):
                    path = root / f"{name}.jsonl"
                    path.write_bytes(content)
                    with self.assertRaises(RepositoryRecoveryRequired):
                        FileEventStore(path)

    def test_identical_duplicate_history_is_reported_but_not_indexed_twice(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "events.jsonl"
            append_raw(path, event("evt_duplicate"))
            append_raw(path, {**event("evt_duplicate"), "recorded_at": "2030-01-01T00:00:00+08:00"})
            store = FileEventStore(path)
            self.assertEqual(store.index_size, 1)
            self.assertTrue(any(item.startswith("duplicate_event_id") for item in store.recovery_report.detected))

    def test_external_growth_rebuilds_but_replace_and_shrink_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "events.jsonl"
            store = FileEventStore(path)
            store.append(event("evt_initial"))
            append_raw(path, event("evt_external"))
            self.assertEqual(store.get_by_id("evt_external")["event_id"], "evt_external")

            replacement = root / "replacement.jsonl"
            append_raw(replacement, event("evt_replaced"))
            os.replace(replacement, path)
            with self.assertRaises(RepositoryConflict):
                store.flush()

            shrink_path = root / "shrink.jsonl"
            shrink_store = FileEventStore(shrink_path)
            shrink_store.append(event("evt_before_shrink"))
            shrink_path.write_bytes(b"")
            with self.assertRaises(RepositoryConflict):
                shrink_store.get_by_id("evt_before_shrink")

    def test_fsync_or_index_failure_is_retryable_without_duplicate(self) -> None:
        for phase in ("after_write", "before_fsync", "after_fsync", "before_index_update"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "events.jsonl"
                store = FileEventStore(path, EventFaultInjector(phase))
                item = event(f"evt_{phase}")
                with self.assertRaises(RepositoryUnavailable):
                    store.append(item)
                retried = store.append(item)
                self.assertEqual(retried.status, "already_exists")
                self.assertEqual(len(path.read_bytes().splitlines()), 1)

    def test_instances_are_isolated_and_close_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = FileEventStore(root / "a.jsonl")
            second = FileEventStore(root / "b.jsonl")
            first.append(event("evt_a"))
            second.append(event("evt_b"))
            first.close()
            first.close()
            with self.assertRaises(RepositoryClosed):
                first.append(event("evt_closed"))
            self.assertIsNone(second.get_by_id("evt_a"))
            self.assertEqual(second.get_by_id("evt_b")["event_id"], "evt_b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
