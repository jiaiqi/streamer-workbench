"""R2 P3 LiveSessionPersistenceService 测试——写穿 + 重启恢复。

覆盖:
- create_session 立即刷写 repo
- queue_request 写穿 (revision 增长)
- record_result 写穿
- grant_entitlement 全 live service 同步刷写
- 重启: 新 LiveServicePersistenceService 实例 + 同 root → 读回 state
  → LiveService 完整重建 (requests/queue/perfs/entitlements/ledger)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.live import (
    KIND_FAN_JOIN,
    RESULT_SUNG,
    RESULT_SKIPPED,
    RequestPolicy,
)
from server.ports.repositories import BackupPolicy, MISSING_REVISION, RepositoryConflict
from server.repositories.live import FileLiveRepository
from server.services.request_policy import RequestPolicyService
from server.services.live_persistence import LiveSessionPersistenceService


def _backup(root: Path) -> BackupPolicy:
    return BackupPolicy(root / "backups", keep=3)


def _policy_factory(rv):
    return RequestPolicyService(policy=RequestPolicy(rule_version=rv))


def _build(root: Path, *, entitlements=None):
    repo = FileLiveRepository(root / "live-sessions", _backup(root))
    return LiveSessionPersistenceService(
        live_repository=repo,
        policy_factory=_policy_factory,
        entitlement_service=entitlements,
    ), repo


class LivePersistenceCreateTests(unittest.TestCase):

    def test_create_session_writes_state_immediately(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc, repo = _build(root)
            live = svc.create_session(rule_version="rv1", title="首播")
            self.assertEqual(live.session.title, "首播")
            # repo 应保存
            snapshot = repo.get(live.session.id)
            assert snapshot is not None
            self.assertEqual(snapshot.value["session"]["rule_version"], "rv1")
            self.assertEqual(snapshot.value["session"]["title"], "首播")

    def test_create_then_queue_writes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc, _ = _build(root)
            live = svc.create_session(rule_version="rv1")
            ent = svc.grant_entitlement(kind=KIND_FAN_JOIN, rule_version="rv1",
                                          quota=2, requester_id="u_1")
            r = svc.queue_request(
                live.session.id,
                requester_name="张三", requester_id="u_1",
                song_id="song_a",
                entitlement_id=ent.id,
                entitlement_kind=KIND_FAN_JOIN,
            )
            # revision 已增长
            rev2 = svc.get_revision(live.session.id)
            self.assertIsNotNone(rev2)
            self.assertNotEqual(rev2, MISSING_REVISION)


class LivePersistenceQueueTests(unittest.TestCase):

    def test_queue_persists_request_and_entitlement(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc, repo = _build(root)
            live = svc.create_session(rule_version="rv1")
            ent = svc.grant_entitlement(kind=KIND_FAN_JOIN, rule_version="rv1",
                                          quota=2, requester_id="u_1")
            r = svc.queue_request(
                live.session.id,
                requester_name="张三", requester_id="u_1", song_id="song_a",
                entitlement_id=ent.id, entitlement_kind=KIND_FAN_JOIN,
            )
            snapshot = repo.get(live.session.id)
            assert snapshot is not None
            state = snapshot.value
            self.assertIn(r.request.id, state["requests"])
            self.assertEqual(len(state["queue"]), 1)
            # entitlement 被核销 1 次
            ent_id = ent.id
            remaining = next(
                e["quota"] - e["consumed"] for e in state["entitlements"].values()
                if e["id"] == ent_id
            )
            self.assertEqual(remaining, 1)


class LivePersistenceRecordTests(unittest.TestCase):

    def test_record_sung_persists_performance(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc, repo = _build(root)
            live = svc.create_session(rule_version="rv1")
            ent = svc.grant_entitlement(kind=KIND_FAN_JOIN, rule_version="rv1",
                                          quota=1, requester_id="u_1")
            r = svc.queue_request(
                live.session.id,
                requester_name="张三", requester_id="u_1",
                song_id="song_a", entitlement_id=ent.id,
                entitlement_kind=KIND_FAN_JOIN,
            )
            svc.record_result(live.session.id, request_id=r.request.id,
                               result=RESULT_SUNG)
            snapshot = repo.get(live.session.id)
            state = snapshot.value
            self.assertIn(r.request.id, state["performances"])
            self.assertEqual(state["queue"], [])  # sung 后队列清空

    def test_record_skipped_refunds_entitlement(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc, repo = _build(root)
            live = svc.create_session(rule_version="rv1")
            ent = svc.grant_entitlement(kind=KIND_FAN_JOIN, rule_version="rv1",
                                          quota=1, requester_id="u_1")
            r = svc.queue_request(
                live.session.id,
                requester_name="张三", requester_id="u_1",
                song_id="song_a", entitlement_id=ent.id,
                entitlement_kind=KIND_FAN_JOIN,
            )
            svc.record_result(live.session.id, request_id=r.request.id,
                               result=RESULT_SKIPPED)
            snapshot = repo.get(live.session.id)
            state = snapshot.value
            remaining = next(
                e["quota"] - e["consumed"] for e in state["entitlements"].values()
            )
            self.assertEqual(remaining, 1)  # 扣 1 退 1


class LivePersistenceRestartTests(unittest.TestCase):

    def test_restart_recovers_full_state(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc1, repo1 = _build(root)
            live = svc1.create_session(rule_version="rv1", title="重启测试")
            ent = svc1.grant_entitlement(kind=KIND_FAN_JOIN, rule_version="rv1",
                                          quota=2, requester_id="u_1")
            r = svc1.queue_request(
                live.session.id,
                requester_name="张三", requester_id="u_1",
                song_id="song_a", entitlement_id=ent.id,
                entitlement_kind=KIND_FAN_JOIN,
            )

            # 重启：用同一个 root 但新 service / 新 repo 实例
            svc2, repo2 = _build(root)
            live2 = svc2.load_session(live.session.id)
            assert live2 is not None
            self.assertEqual(live2.session.title, "重启测试")
            self.assertEqual(live2.session.rule_version, "rv1")
            # queue 恢复
            self.assertEqual(len(live2._queue), 1)
            # entitlements 恢复
            ents = list(svc2.entitlements().granted())
            self.assertEqual(len(ents), 1)
            self.assertEqual(ents[0].remaining(), 1)


class LivePersistenceCASTests(unittest.TestCase):
    """revision CAS: 上层并发写穿应被 repo 拒绝。"""

    def test_concurrent_save_rejected(self):
        """两个持久化服务实例并发刷写同一 session: 第二个应被 repo 拒绝。"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc1, repo1 = _build(root)
            svc2, repo2 = _build(root)
            live = svc1.create_session(rule_version="rv1")
            sid = live.session.id

            # svc2 必须先 load 才能调 queue (但 load 后会拿当前最新 revision)
            svc2.load_session(sid)

            # svc1 写之后, 直接手工让 svc2 持有过期 revision, 模拟并发写
            svc1.queue_request(sid, requester_name="a", song_id="s1")
            svc2._current_revision[sid] = MISSING_REVISION
            with self.assertRaises(RepositoryConflict):
                svc2.queue_request(sid, requester_name="b", song_id="s2")


class LivePersistenceCloseTests(unittest.TestCase):

    def test_close_session_persists_state(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            svc, repo = _build(root)
            live = svc.create_session(rule_version="rv1")
            svc.close_session(live.session.id, reason="收工")
            snapshot = repo.get(live.session.id)
            assert snapshot is not None
            self.assertEqual(snapshot.value["session"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
