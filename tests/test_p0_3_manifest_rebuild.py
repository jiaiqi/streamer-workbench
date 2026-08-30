"""P0-3：Manifest 视为派生索引测试。

覆盖 LiveRepository 的 _rebuild_manifest_from_disk 行为：
- 磁盘有但 manifest 没有 → 加到 manifest（orphaned state picked up）
- manifest 有但磁盘没有 → 从 manifest 移除（missing state cleaned）
- 两边都有 → 保留（不修改）
- 启动时 recover() 包含 manifest rebuild 结果
- 非法目录名（.trash / .recovery）不被扫
- 目录无 state.json → 不被识别为 session
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.repositories.live import FileLiveRepository  # noqa: E402
from server.ports.repositories import BackupPolicy  # noqa: E402


def _make_repo(td: Path) -> FileLiveRepository:
    return FileLiveRepository(
        td, BackupPolicy(td / "backups"))


def _write_state(td: Path, session_id: str, payload: dict | None = None) -> None:
    """手动写一个 state.json 到 <td>/<session_id>/state.json。"""
    sdir = td / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    data = payload or {
        "schema_version": 1,
        "session": {"id": session_id, "state": "active",
                    "started_at": "2026-08-30T10:00:00",
                    "rule_version": "v1"},
        "requests": {},
        "queue": [],
        "performances": {},
        "entitlements": {},
        "consecutive_bumps": 0,
        "ledger": [],
    }
    (sdir / "state.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read_manifest(td: Path) -> dict:
    p = td / "manifest.json"
    if not p.exists():
        return {"schema_version": 1, "sessions": []}
    return json.loads(p.read_text(encoding="utf-8"))


class LiveManifestRebuildTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_recover_picks_up_orphaned_state_on_disk(self):
        """磁盘有 state.json，manifest 没有 → 启动时加入 manifest。"""
        _write_state(self.td, "sess_orphan_1")
        _write_state(self.td, "sess_orphan_2")
        # repo.__init__ 自动调 recover() 一次（构造期间）；
        # 取出第一次 recover 的 report 来验
        repo = _make_repo(self.td)
        first_report = repo._report
        # 验证 manifest 现在包含两个孤儿
        m = _read_manifest(self.td)
        self.assertIn("sess_orphan_1", m["sessions"])
        self.assertIn("sess_orphan_2", m["sessions"])
        detected = " ".join(first_report.detected)
        self.assertIn("orphaned_state_picked_up:sess_orphan_1", detected)
        self.assertIn("orphaned_state_picked_up:sess_orphan_2", detected)

    def test_recover_removes_manifest_entries_without_disk(self):
        """manifest 有但磁盘没有 → 启动时从 manifest 移除。"""
        repo = _make_repo(self.td)
        # 模拟"manifest 里有但磁盘没有"：手动改 manifest.json
        m = _read_manifest(self.td)
        m["sessions"] = ["sess_ghost_1", "sess_ghost_2"]
        m.setdefault("revisions", {})["sess_ghost_1"] = "r1"
        m["revisions"]["sess_ghost_2"] = "r2"
        (self.td / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        report = repo.recover()
        m = _read_manifest(self.td)
        self.assertNotIn("sess_ghost_1", m["sessions"])
        self.assertNotIn("sess_ghost_2", m["sessions"])
        self.assertNotIn("sess_ghost_1", m.get("revisions", {}))
        self.assertNotIn("sess_ghost_2", m.get("revisions", {}))
        detected = " ".join(report.detected)
        self.assertIn("missing_state_cleaned:sess_ghost_1", detected)
        self.assertIn("missing_state_cleaned:sess_ghost_2", detected)

    def test_recover_keeps_consistent_entries_untouched(self):
        """磁盘和 manifest 一致 → 不动。"""
        _write_state(self.td, "sess_good")
        repo = _make_repo(self.td)
        m = _read_manifest(self.td)
        m["sessions"] = ["sess_good"]
        m.setdefault("revisions", {})["sess_good"] = "original_rev"
        (self.td / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        report = repo.recover()
        m_after = _read_manifest(self.td)
        self.assertEqual(m_after["sessions"], ["sess_good"])
        self.assertEqual(m_after["revisions"]["sess_good"], "original_rev")
        detected = " ".join(report.detected)
        self.assertNotIn("orphaned_state_picked_up", detected)
        self.assertNotIn("missing_state_cleaned", detected)

    def test_mixed_recovery(self):
        """混合场景：磁盘有 A/B/C，manifest 有 B/D。期望：加 A C，删 D，保留 B。"""
        _write_state(self.td, "sess_A")
        _write_state(self.td, "sess_B")
        _write_state(self.td, "sess_C")
        repo = _make_repo(self.td)
        m = _read_manifest(self.td)
        m["sessions"] = ["sess_B", "sess_D"]
        m.setdefault("revisions", {})["sess_B"] = "rB"
        m["revisions"]["sess_D"] = "rD"
        (self.td / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        report = repo.recover()
        m_after = _read_manifest(self.td)
        self.assertIn("sess_A", m_after["sessions"])
        self.assertIn("sess_B", m_after["sessions"])
        self.assertIn("sess_C", m_after["sessions"])
        self.assertNotIn("sess_D", m_after["sessions"])
        self.assertEqual(m_after["revisions"]["sess_B"], "rB")
        self.assertNotIn("sess_D", m_after.get("revisions", {}))

    def test_ignores_hidden_directories(self):
        """.trash / .recovery 目录不被扫为 session。"""
        trash = self.td / ".trash"
        (trash / "old_session").mkdir(parents=True)
        (trash / "old_session" / "state.json").write_text("{}", encoding="utf-8")
        (self.td / "no_state_here").mkdir()
        _write_state(self.td, "sess_real")
        repo = _make_repo(self.td)
        report = repo.recover()
        m = _read_manifest(self.td)
        self.assertIn("sess_real", m["sessions"])
        self.assertNotIn("old_session", m["sessions"])
        self.assertNotIn("no_state_here", m["sessions"])

    def test_ignores_invalid_session_id_directory(self):
        """manifest 里有非法的 ".." / "." → 启动时静默清掉，不抛异常。"""
        repo = _make_repo(self.td)
        m = _read_manifest(self.td)
        m["sessions"] = ["..", "."]
        (self.td / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
        # 不应抛异常
        report = repo.recover()
        m_after = _read_manifest(self.td)
        self.assertNotIn("..", m_after["sessions"])
        self.assertNotIn(".", m_after["sessions"])

    def test_added_session_gets_revision_from_state(self):
        """加进来的 session 应该有 revision（基于 state.json 的 hash）。"""
        _write_state(self.td, "sess_with_rev")
        repo = _make_repo(self.td)
        repo.recover()
        m = _read_manifest(self.td)
        rev = m.get("revisions", {}).get("sess_with_rev")
        self.assertIsNotNone(rev)
        self.assertIsInstance(rev, str)
        self.assertGreater(len(rev), 0)

    def test_empty_disk_no_op(self):
        """磁盘空 + manifest 空 → no-op。"""
        repo = _make_repo(self.td)
        report = repo.recover()
        self.assertEqual(report.detected, ())
        self.assertEqual(report.recovered, ())


if __name__ == "__main__":
    unittest.main()
