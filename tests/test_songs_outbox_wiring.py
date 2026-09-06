"""P0-2c：SongApplicationService CRUD 事件经 LocalOutbox 落盘的接线测试。

canonical 顺序（core/outbox.py 设计）：事件先入 outbox（fsync 持久）→
songs.json 原子落盘 → drain 到 events.jsonl（按 event_id 幂等）。

覆盖：
- 正常路径：state 保存 + 事件已 drain 进 events.jsonl + outbox 清空
- drain 失败（events.append 抛错）：state 仍保存、outbox 保留，之后 drain 补发
- 崩溃窗口（outbox.append 后、songs.save 前）：事件留在 outbox，
  重启 drain 补发（幽灵窗口与旧行为等价，文档化）
- 不注入 outbox：行为与旧实现完全一致（回归保护）
- seed_sample_songs：批量事件一次 drain
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.outbox import LocalOutbox  # noqa: E402
from server.ports.repositories import BackupPolicy  # noqa: E402
from server.repositories.events import FileEventStore  # noqa: E402
from server.repositories.songs import FileSongRepository  # noqa: E402
from server.services.songs import SongApplicationService  # noqa: E402


def _backup(root: Path) -> BackupPolicy:
    return BackupPolicy(root / "backups", keep=3)


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


def _has_song(repo, title: str) -> bool:
    return any(s.title == title for s in repo.load().value.songs)


class SongsOutboxWiringTests(unittest.TestCase):

    def _build(self, root: Path, events_path: Path):
        repo = FileSongRepository(root / "songs.json", _backup(root))
        events = FileEventStore(events_path)
        outbox = LocalOutbox(root / "outbox.jsonl")
        svc = SongApplicationService(
            song_repository=repo, event_store=events, outbox=outbox)
        return svc, repo, events, outbox

    def test_normal_flow_state_saved_event_drained_outbox_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)
            svc.create({"title": "晴天", "artists": ["周杰伦"]})
            # state 已保存
            self.assertTrue(_has_song(repo, "晴天"))
            # 事件已 drain
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("song_added", types)
            # outbox 已清空
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_drain_failure_preserves_outbox_state_still_saved(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)

            def failing_append(self, ev):
                raise RuntimeError("events.jsonl 磁盘故障")

            with patch.object(FileEventStore, "append", failing_append):
                svc.create({"title": "晴天", "artists": ["周杰伦"]})
            # state 仍然保存（业务事实不因事件通道故障回滚）
            self.assertTrue(_has_song(repo, "晴天"))
            # 事件保留在 outbox
            pending = _read_outbox(root / "outbox.jsonl")
            self.assertTrue(any(e["event"]["type"] == "song_added"
                                for e in pending))
            self.assertEqual(_read_events(events_path), [])
            # 恢复后 drain 补发 + 清空
            outbox.drain(events.append)
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("song_added", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_crash_between_outbox_append_and_save_recovers_on_next_start(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)
            original_save = type(repo).save
            with patch.object(type(repo), "save",
                              lambda self, *a, **k: (_ for _ in ()).throw(
                                  RuntimeError("simulated crash"))):
                with self.assertRaises(RuntimeError):
                    svc.create({"title": "晴天", "artists": ["周杰伦"]})
            # outbox 里已有事件（fsync 持久）
            pending = _read_outbox(root / "outbox.jsonl")
            self.assertTrue(any(e["event"]["type"] == "song_added"
                                for e in pending))
            # 重启语义：drain 补发（app.lifespan P0-2b 同逻辑）
            outbox.drain(events.append)
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("song_added", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_no_outbox_injected_keeps_legacy_behavior(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            repo = FileSongRepository(root / "songs.json", _backup(root))
            events = FileEventStore(events_path)
            svc = SongApplicationService(
                song_repository=repo, event_store=events)
            svc.create({"title": "晴天", "artists": ["周杰伦"]})
            types = [e["type"] for e in _read_events(events_path)]
            self.assertIn("song_added", types)
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])

    def test_seed_sample_songs_batches_all_events_through_outbox(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            events_path = root / "events.jsonl"
            svc, repo, events, outbox = self._build(root, events_path)
            svc.seed_sample_songs()
            # state 已保存
            self.assertTrue(repo.load().value.songs)
            # 事件已 drain（seed 曲库多条 song_added）
            types = [e["type"] for e in _read_events(events_path)]
            self.assertTrue(all(t == "song_added" for t in types))
            self.assertTrue(types)
            # outbox 已清空
            self.assertEqual(_read_outbox(root / "outbox.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
