"""P0-2b outbox lifespan 集成测试。

验证：
- 启动时 outbox 文件存在 → drain 到 events
- outbox 空 → no-op
- drain 失败（events.append 抛错） → outbox 保留
- 每次启动都跑一次 drain（幂等）
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_outbox(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _setup_minimal_data_root(td: Path) -> Path:
    """让 create_app 不报"需要 test 模式 data_root"——写最小数据。"""
    (td / "events.jsonl").touch()
    (td / "settings.json").write_text(
        '{"output_dir":"/tmp","default_canvas":"9:20","default_theme":"海洋柔光",'
        '"font_path":"/tmp/font.ttf","backup_count":0,"render_threads":1,'
        '"schemaVersion":1}', encoding="utf-8")
    (td / "songs.json").write_text(
        '{"schema_version":5,"songs":[]}', encoding="utf-8")
    return td


class OutboxLifespanDrainTests(unittest.TestCase):
    """create_app lifespan 启动时把 outbox 里的事件 drain 到 events.jsonl。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.data_root = Path(self._td.name) / "data"
        self.data_root.mkdir(parents=True, exist_ok=True)
        _setup_minimal_data_root(self.data_root)

    def tearDown(self):
        self._td.cleanup()

    def _create_app_and_run_lifespan(self):
        from server.app import create_app
        app = create_app(AppConfig(
            PROJECT_ROOT, mode="test", data_root=self.data_root))
        async def _run():
            async with app.router.lifespan_context(app):
                pass
        asyncio.run(_run())
        return app

    def _event(self, event_id: str, type_: str = "test") -> dict:
        return {
            "outbox_id": f"obx_{event_id}",
            "event": {
                "schema_version": 2,
                "event_id": event_id,
                "occurred_at": "2026-08-30T10:00:00",
                "recorded_at": "2026-08-30T10:00:00",
                "type": type_,
                "source": "outbox-drain-test",
            },
            "enqueued_at": "2026-08-30T10:00:00",
            "context": {},
        }

    def test_drain_on_startup_moves_outbox_to_events(self):
        outbox_path = self.data_root / "outbox.jsonl"
        _write_outbox(outbox_path, [
            self._event("evt_a"),
            self._event("evt_b"),
            self._event("evt_c", "test_two"),
        ])
        self._create_app_and_run_lifespan()
        events = _read_events(self.data_root / "events.jsonl")
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["event_id"], "evt_a")
        self.assertEqual(events[1]["event_id"], "evt_b")
        self.assertEqual(events[2]["event_id"], "evt_c")
        self.assertEqual(events[2]["type"], "test_two")
        # outbox 文件应被 truncate（drain 成功后用 os.replace + unlink 删除）
        self.assertFalse(outbox_path.exists())

    def test_empty_outbox_noop(self):
        # 不预填 outbox（不存在）
        self._create_app_and_run_lifespan()
        events = _read_events(self.data_root / "events.jsonl")
        self.assertEqual(events, [])

    def test_drain_failure_preserves_outbox(self):
        outbox_path = self.data_root / "outbox.jsonl"
        _write_outbox(outbox_path, [
            self._event("evt_x"),
            self._event("evt_y"),
        ])
        # mock FileEventStore.append 第一次失败
        from server.repositories.events import FileEventStore
        call_count = {"n": 0}
        original_append = FileEventStore.append

        def failing_append(self, ev):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated event store failure")
            return original_append(self, ev)

        with patch.object(FileEventStore, "append", failing_append):
            self._create_app_and_run_lifespan()

        # 第 1 条失败后 outbox 保留（drain 停止）
        remaining = _read_events(outbox_path)
        self.assertEqual(len(remaining), 2)
        # events.jsonl 应是空的（drain 失败时还未写）
        events = _read_events(self.data_root / "events.jsonl")
        self.assertEqual(events, [])
        # 重启：正常 events.append 应能清空 outbox
        self._create_app_and_run_lifespan()
        remaining_after = _read_events(outbox_path)
        self.assertEqual(len(remaining_after), 0)
        events_after = _read_events(self.data_root / "events.jsonl")
        # 第 1 次失败未写 events.jsonl；第 2 次启动重试 → 全部 2 条写入
        self.assertEqual(len(events_after), 2)

    def test_drain_idempotent_across_two_starts(self):
        outbox_path = self.data_root / "outbox.jsonl"
        _write_outbox(outbox_path, [self._event("evt_z")])
        # 第一次启动
        self._create_app_and_run_lifespan()
        events1 = _read_events(self.data_root / "events.jsonl")
        self.assertEqual(len(events1), 1)
        # 第二次启动（无新 outbox；已被 truncate）
        self._create_app_and_run_lifespan()
        events2 = _read_events(self.data_root / "events.jsonl")
        # 仍是 1 条（不重复）
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0]["event_id"], "evt_z")


if __name__ == "__main__":
    unittest.main()
