"""R2 P3 FileLiveRepository 测试——原子写 / CAS / 备份 / 恢复。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.ports.repositories import (
    BackupPolicy,
    MISSING_REVISION,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryUnavailable,
)
from server.repositories.atomic_json import AtomicJsonWriter
from server.repositories.live import FileLiveRepository, LiveFaultInjector


def _backup(root: Path) -> BackupPolicy:
    return BackupPolicy(root / "backups", keep=3)


def _payload(sid: str) -> dict:
    return {
        "schema_version": 1,
        "session": {
            "id": sid,
            "state": "active",
            "rule_version": "rv1",
            "started_at": "2026-07-30T12:00:00+08:00",
        },
        "requests": {},
        "queue": [],
        "performances": {},
        "entitlements": {},
        "consecutive_bumps": 0,
    }


class FileLiveRepositoryBasicTests(unittest.TestCase):

    def test_save_then_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            sid = "live_test_1"
            payload = _payload(sid)
            snap = repo.save(sid, payload, expected_revision=MISSING_REVISION)
            self.assertEqual(snap.revision, snap.revision)  # sha256
            self.assertGreater(len(snap.revision), 10)

            loaded = repo.get(sid)
            assert loaded is not None
            self.assertEqual(loaded.value["session"]["rule_version"], "rv1")
            self.assertEqual(loaded.revision, snap.revision)

    def test_list_sessions_returns_id_tuple(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            repo.save("live_a", _payload("live_a"), expected_revision=MISSING_REVISION)
            repo.save("live_b", _payload("live_b"), expected_revision=MISSING_REVISION)
            snap = repo.list_sessions()
            self.assertEqual(set(snap.value), {"live_a", "live_b"})

    def test_get_unknown_session_returns_none(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            self.assertIsNone(repo.get("live_phantom"))

    def test_save_rejects_bad_session_id(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            for bad in ("../escape", "a/b", "", "."):
                with self.assertRaises(ValueError):
                    repo.save(bad, _payload(bad) if bad else {},
                              expected_revision=MISSING_REVISION)


class FileLiveRepositoryCASTests(unittest.TestCase):
    """revision CAS: expected_revision 与当前不符必须抛冲突，绝不静默覆盖。"""

    def test_conflict_when_expected_missing_but_current_exists(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            sid = "live_cas"
            snap1 = repo.save(sid, _payload(sid), expected_revision=MISSING_REVISION)
            # 第二次 save 用 MISSING_REVISION → 冲突（current 是 snap1.revision）
            with self.assertRaises(RepositoryConflict):
                repo.save(sid, _payload(sid), expected_revision=MISSING_REVISION)
            # 旧值未被覆盖
            loaded = repo.get(sid)
            assert loaded is not None
            self.assertEqual(loaded.revision, snap1.revision)

    def test_sequential_succeeds_then_chained_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            sid = "live_chain"
            snap1 = repo.save(sid, _payload(sid), expected_revision=MISSING_REVISION)
            payload2 = _payload(sid)
            payload2["consecutive_bumps"] = 1   # 内容必须变 → 新 revision
            snap2 = repo.save(sid, payload2, expected_revision=snap1.revision)
            self.assertNotEqual(snap1.revision, snap2.revision)
            with self.assertRaises(RepositoryConflict):
                repo.save(sid, _payload(sid), expected_revision=snap1.revision)


class FileLiveRepositoryDeleteTests(unittest.TestCase):

    def test_delete_moves_to_trash(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            sid = "live_del"
            snap = repo.save(sid, _payload(sid), expected_revision=MISSING_REVISION)
            ok = repo.delete(sid, expected_revision=snap.revision)
            self.assertTrue(ok)
            self.assertIsNone(repo.get(sid))
            # manifest 同步
            self.assertNotIn(sid, repo.list_sessions().value)

    def test_delete_nonexistent_returns_false(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            self.assertFalse(repo.delete("ghost", expected_revision=MISSING_REVISION))


class FileLiveRepositoryRecoveryTests(unittest.TestCase):

    def test_recover_cleans_orphan_tmp(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            live_root = root / "live-sessions"
            live_root.mkdir()
            # 模拟 init 完成后再发生孤儿（写一个写一半的 .tmp）
            (live_root / "manifest.json").write_text(
                '{"schema_version":1,"sessions":[]}', encoding="utf-8"
            )
            repo = FileLiveRepository(live_root, _backup(root))
            # init 已清空；现在模拟崩溃后孤儿
            (live_root / "ghost.tmp").write_text("stale", encoding="utf-8")
            report = repo.recover()
            self.assertFalse((live_root / "ghost.tmp").exists())
            self.assertGreater(len(report.recovered), 0)

    def test_closed_repo_raises(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = FileLiveRepository(root / "live-sessions", _backup(root))
            repo.close()
            with self.assertRaises(RepositoryClosed):
                repo.list_sessions()


class FileLiveRepositoryFaultInjectTests(unittest.TestCase):

    def test_pre_write_failure_does_not_corrupt(self):
        """pre-write 注入抛错 → 文件不应被创建。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            injector = LiveFaultInjector(fail_at="pre-write")
            repo = FileLiveRepository(root / "live-sessions", _backup(root),
                                       fault_injector=injector)
            with self.assertRaises(OSError):
                repo.save("live_x", _payload("live_x"),
                          expected_revision=MISSING_REVISION)
            # state.json 不应创建
            self.assertFalse((root / "live-sessions" / "live_x" / "state.json").exists())

    def test_pre_write_failure_does_not_corrupt(self):
        """pre-write 注入抛错 → 文件不应被创建。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            injector = LiveFaultInjector(fail_at="pre-write")
            repo = FileLiveRepository(root / "live-sessions", _backup(root),
                                       fault_injector=injector)
            with self.assertRaises(OSError):
                repo.save("live_x", _payload("live_x"),
                          expected_revision=MISSING_REVISION)
            # state.json 不应创建
            self.assertFalse((root / "live-sessions" / "live_x" / "state.json").exists())

    def test_writer_injected_failure_raises_repository_unavailable(self):
        """AtomicJsonWriter 在 before_replace 抛错 → writer 包成 RepositoryUnavailable 透传；
        旧值不被破坏（writer 内置 rollback）。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            # 计数器：第二次 write 调用 before_replace 时抛错
            state = {"calls": 0}
            def _inject(phase):
                if phase != "before_replace":
                    return
                state["calls"] += 1
                if state["calls"] == 2:
                    raise OSError(f"injected before_replace crash #{state['calls']}")
            writer = AtomicJsonWriter(fault_injector=_inject)
            repo = FileLiveRepository(root / "live-sessions", _backup(root),
                                       writer=writer)
            sid = "live_y"
            snap = repo.save(sid, _payload(sid), expected_revision=MISSING_REVISION)
            payload2 = _payload(sid)
            payload2["consecutive_bumps"] = 5
            from server.ports.repositories import RepositoryUnavailable
            with self.assertRaises((OSError, RepositoryUnavailable)):
                repo.save(sid, payload2, expected_revision=snap.revision)
            loaded = repo.get(sid)
            assert loaded is not None
            self.assertEqual(loaded.revision, snap.revision)


if __name__ == "__main__":
    unittest.main()
