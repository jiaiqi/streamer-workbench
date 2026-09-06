"""P0-2c：导出任务 poster_exported 事件经 LocalOutbox 落盘的接线测试。

后台线程 run_export_job 收尾时：事件先入 outbox（fsync 持久）→ 立即 drain
到 event_store（按 event_id 幂等）。PNG 文件此时已落盘 = 业务事实。

覆盖：
- 正常路径：PNG 落盘 + 事件已 drain + outbox 清空
- drain 失败（event_store.append 抛错）：job 状态 error、outbox 保留，
  之后 drain 补发
- 无 outbox 回归：行为与旧实现一致（直写 event_store）
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.songs import Song, SongLibrary  # noqa: E402
from core.outbox import LocalOutbox  # noqa: E402
from core.spec import get_canvas_spec  # noqa: E402
from server.ports.repositories import StoredSnapshot  # noqa: E402
from server.repositories.events import FileEventStore  # noqa: E402
from server.services.export import (  # noqa: E402
    ExportJobInput,
    ExportTarget,
    create_export_snapshot,
    run_export_job,
)
from server.services.render_document import build_render_document  # noqa: E402
from core.themes.loader import load_themes  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT = PROJECT_ROOT / "fonts" / "MaokenAssortedSans.ttf"


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


def _job_input(root: Path, events, outbox):
    document = build_render_document(
        song_snapshot=StoredSnapshot(
            SongLibrary([Song(
                "冻结歌曲", id="song_00000000000000000000000000000001",
                artists=["原歌手"], tags=["原标签"])]), "songs-1"),
        theme=load_themes(str(PROJECT_ROOT / "themes"))["海洋柔光"],
        layout_id="grid-wrap", canvas=get_canvas_spec("标准 9:16"), page=1,
        font_path=str(FONT), settings_revision="settings-1",
        parameters={"nested": {"items": [1, 2]}},
    )
    target = root / "out.png"
    snapshot = create_export_snapshot(
        job_id="job-outbox-test", documents=(document,),
        targets=(ExportTarget(target, "海洋柔光", 1),))
    state = {"status": "running", "done": 0, "total": 1, "current": "",
             "files": [], "output_dir": str(root), "total_ms": None,
             "error": None}
    return ExportJobInput(snapshot, events, state, outbox=outbox), state, target


class ExportOutboxWiringTests(unittest.TestCase):

    def test_normal_flow_png_written_event_drained_outbox_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            events = FileEventStore(events_path)
            outbox = LocalOutbox(root / "outbox.jsonl")
            job_input, state, target = _job_input(root, events, outbox)
            run_export_job(job_input)
            self.assertEqual(state["status"], "done")
            self.assertTrue(target.is_file())
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("poster_exported", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_drain_failure_outbox_preserved_job_still_done(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            events = FileEventStore(events_path)
            outbox = LocalOutbox(root / "outbox.jsonl")
            job_input, state, target = _job_input(root, events, outbox)

            def failing_append(self, ev):
                raise RuntimeError("events.jsonl 磁盘故障")

            with patch.object(FileEventStore, "append", failing_append):
                run_export_job(job_input)
            # PNG 已落盘（业务事实）；drain 失败被 LocalOutbox 内部吞掉
            # （记日志 + 保留 outbox，不重抛）→ job 保持 done
            self.assertTrue(target.is_file())
            self.assertEqual(state["status"], "done")
            # 事件保留在 outbox，恢复后补发
            pending = _read_outbox(root / "outbox.jsonl")
            self.assertTrue(any(e["event"]["type"] == "poster_exported"
                                for e in pending))
            self.assertEqual(_read_events(events_path), [])
            outbox.drain(events.append)
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("poster_exported", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_crash_after_outbox_append_event_survives_restart(self):
        """模拟崩溃窗口：事件已入 outbox（fsync 持久）、drain 前进程死亡。

        下次启动 lifespan drain（P0-2b）补发——事件不丢。
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            events = FileEventStore(events_path)
            outbox = LocalOutbox(root / "outbox.jsonl")
            job_input, state, target = _job_input(root, events, outbox)

            def crashing_drain(self, sink, **kwargs):
                raise RuntimeError("simulated crash after outbox.append")

            with patch.object(LocalOutbox, "drain", crashing_drain):
                run_export_job(job_input)
            self.assertTrue(target.is_file())
            # 崩溃等价物：run_export_job 的 except 把 RuntimeError 记为 job error
            self.assertEqual(state["status"], "error")
            # 事件已在 outbox 持久化
            pending = _read_outbox(root / "outbox.jsonl")
            self.assertTrue(any(e["event"]["type"] == "poster_exported"
                                for e in pending))
            self.assertEqual(_read_events(events_path), [])
            # 重启语义：lifespan drain 补发
            outbox.drain(events.append)
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("poster_exported", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_no_outbox_keeps_legacy_direct_append(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            events = FileEventStore(events_path)
            job_input, state, target = _job_input(root, events, None)
            run_export_job(job_input)
            self.assertEqual(state["status"], "done")
            self.assertTrue(target.is_file())
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("poster_exported", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
