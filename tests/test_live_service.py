"""R2 P3 LiveService 测试——start / queue / record / duplicate / close。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.live import (
    EntitlementGrant,
    KIND_FAN_JOIN,
    KIND_GIFT_EXCHANGE,
    KIND_MANUAL,
    LiveSession,
    RequestPolicy,
    RESULT_CANCELLED,
    RESULT_POSTPONED,
    RESULT_REQUESTED,
    RESULT_SKIPPED,
    RESULT_SUNG,
    RESULT_UNKNOWN,
    SESSION_ACTIVE,
    SESSION_CLOSED,
    SongRequest,
)
from server.services.entitlements import EntitlementService
from server.services.live import (
    LiveService,
    LiveServiceError,
    SessionClosed,
    SessionNotFound,
    UnknownRequest,
)
from server.services.request_policy import RequestPolicyService


class _FakeEventStore:
    """录制所有 append 调用。"""
    def __init__(self):
        self.events: list[dict] = []

    def append(self, event):
        self.events.append(event)

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]


def _build_live(rule_version: str = "rv1", max_bumps: int = 3):
    """最小可工作三件套：LiveService + 内存事件流。"""
    session = LiveSession(rule_version=rule_version)
    policy = RequestPolicy(rule_version=rule_version,
                            fairness_max_consecutive_bumps=max_bumps)
    policy_svc = RequestPolicyService(policy=policy)
    ent_svc = EntitlementService()
    events = _FakeEventStore()
    live = LiveService(session=session, policy_service=policy_svc,
                       entitlement_service=ent_svc, event_store=events)
    return live, ent_svc, events, policy


class LiveServiceQueueTests(unittest.TestCase):

    def test_basic_queue_with_entitlement(self):
        live, ent, events, _ = _build_live()
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1",
                       quota=3, requester_id="u_1")
        r = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a", entitlement_id=e.id,
            entitlement_kind=KIND_FAN_JOIN,
        )
        self.assertEqual(r.entry.position, 1)
        self.assertTrue(r.decision.allowed)
        self.assertEqual(events.types()[0], "queue_added")
        # entitlement 必须被核销 1 次
        self.assertEqual(ent.get(e.id).remaining(), 2)

    def test_queue_without_entitlement_still_allowed(self):
        """无权益入队仍然允许（手动 / 主播加歌）。
        （注：当前实现核销仅在 entitlement_id 提供时发生）"""
        live, _, events, _ = _build_live()
        r = live.queue_request(
            requester_name="主播", song_id="song_a",
        )
        self.assertTrue(r.decision.allowed)
        self.assertEqual(events.types()[0], "queue_added")

    def test_duplicate_same_song_and_requester_merges(self):
        """v3 §6.5 duplicate_merged：同 (session, song, requester) 二次入队合并。"""
        live, ent, events, _ = _build_live()
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1",
                       quota=2, requester_id="u_1")
        r1 = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a", entitlement_id=e.id,
        )
        r2 = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a",
        )
        # queue 仍只 1 个 entry
        self.assertEqual(live.queue_size, 1)
        # 但写了 duplicate_merged 事件
        self.assertIn("request_duplicate_merged", events.types())
        # 第二次的核销**不应该**再次扣（没有 entitlement_id）
        self.assertEqual(ent.get(e.id).remaining(), 1)


class LiveServiceRecordTests(unittest.TestCase):

    def test_sung_records_performance_and_doesnt_refund(self):
        live, ent, events, _ = _build_live()
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1",
                       quota=1, requester_id="u_1")
        r = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a", entitlement_id=e.id,
            entitlement_kind=KIND_FAN_JOIN,
        )
        # 演唱成功
        result = live.record_result(
            request_id=r.request.id, result=RESULT_SUNG,
        )
        self.assertEqual(result.performance.result, RESULT_SUNG)
        self.assertFalse(result.refunded)  # sung 不退
        # queue 应清空
        self.assertEqual(live.queue_size, 0)
        # 事件顺序：queue_added → performance_sung
        self.assertEqual(events.types()[-1], "performance_sung")

    def test_skipped_refunds_entitlement(self):
        live, ent, events, _ = _build_live()
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1",
                       quota=2, requester_id="u_1")
        r = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a", entitlement_id=e.id,
            entitlement_kind=KIND_FAN_JOIN,
        )
        result = live.record_result(
            request_id=r.request.id, result=RESULT_SKIPPED,
            reason="曲谱缺失",
        )
        self.assertTrue(result.refunded)
        # 扣 1 + 退 1 = remaining 2
        self.assertEqual(ent.get(e.id).remaining(), 2)
        self.assertIn("entitlement_refunded", events.types())

    def test_cancelled_refunds_entitlement(self):
        live, ent, _, _ = _build_live()
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1",
                       quota=1, requester_id="u_1")
        r = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a", entitlement_id=e.id,
            entitlement_kind=KIND_FAN_JOIN,
        )
        result = live.record_result(
            request_id=r.request.id, result=RESULT_CANCELLED,
        )
        self.assertTrue(result.refunded)
        self.assertEqual(ent.get(e.id).remaining(), 1)

    def test_unknown_refunds_entitlement_and_marks_learning_candidate(self):
        """v3 §6.5: unknown 是"主播不会唱" → learning_candidate，权益应返还"""
        live, ent, _, _ = _build_live()
        e = ent.grant(kind=KIND_GIFT_EXCHANGE, rule_version="rv1",
                       quota=1, requester_id="u_1")
        r = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_x", entitlement_id=e.id,
            entitlement_kind=KIND_GIFT_EXCHANGE,
        )
        result = live.record_result(
            request_id=r.request.id, result=RESULT_UNKNOWN,
        )
        self.assertTrue(result.refunded)
        self.assertEqual(ent.get(e.id).remaining(), 1)

    def test_unknown_request_raises(self):
        live, _, _, _ = _build_live()
        with self.assertRaises(UnknownRequest):
            live.record_result(
                request_id="phantom", result=RESULT_SUNG,
            )


class LiveServiceSessionTests(unittest.TestCase):

    def test_close_records_session_closed_event(self):
        live, _, events, _ = _build_live()
        live.close(reason="收工")
        self.assertEqual(live.session.state, SESSION_CLOSED)
        self.assertEqual(events.types()[-1], "session_closed")

    def test_close_after_close_raises(self):
        live, _, _, _ = _build_live()
        live.close()
        with self.assertRaises(SessionClosed):
            live.close()

    def test_queue_after_close_raises(self):
        live, _, _, _ = _build_live()
        live.close()
        with self.assertRaises(SessionClosed):
            live.queue_request(requester_name="迟来", song_id="song_y")


class LiveServiceConcurrencyTests(unittest.TestCase):

    def test_duplicate_event_appended_each_dup(self):
        """大量 duplicate_merged: 队列仍只 1 entry，但写多个事件。"""
        live, _, events, _ = _build_live()
        for _ in range(5):
            live.queue_request(requester_name="重复哥", song_id="song_z")
        self.assertEqual(live.queue_size, 1)
        # 1 个 queue_added + 4 个 duplicate_merged
        self.assertEqual(events.types().count("queue_added"), 1)
        self.assertEqual(events.types().count("request_duplicate_merged"), 4)


class LiveServiceIntegrityTests(unittest.TestCase):

    def test_entitlement_quota_exceeded_rejects_queue(self):
        """quota 不足时入队拒绝，请求和 entry 都不落地。"""
        live, ent, _, _ = _build_live()
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1",
                       quota=1, requester_id="u_1")
        # 第一次入队
        r1 = live.queue_request(
            requester_name="张三", requester_id="u_1",
            song_id="song_a", entitlement_id=e.id,
            entitlement_kind=KIND_FAN_JOIN,
        )
        self.assertIsNotNone(r1)
        # 第二次 quota 已用尽：拒绝
        with self.assertRaises(LiveServiceError):
            live.queue_request(
                requester_name="李四", requester_id="u_2",
                song_id="song_b", entitlement_id=e.id,
                entitlement_kind=KIND_FAN_JOIN,
            )

    def test_grant_rejects_zero_quota(self):
        live, ent, _, _ = _build_live()
        # 业务规则：quota 必须 >= 1
        with self.assertRaises(Exception):
            ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=0)


if __name__ == "__main__":
    unittest.main()
