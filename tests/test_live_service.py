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


# ── M2.4 点歌条件集成测试 ──


class M24LiveServiceIntegrationTests(unittest.TestCase):
    """验证 queue_request 把 policy 的 4 字段实际生效到端到端流程。"""

    def _build(self, **policy_overrides):
        from dataclasses import replace
        live, ent, events, policy = _build_live()
        if policy_overrides:
            new_policy = replace(policy, **policy_overrides)
            live.update_policy(new_policy=new_policy)
        return live, ent, events

    def test_max_queue_length_actual_blocks_4th_enqueue(self):
        from core.data.live import KIND_FAN_JOIN
        live, ent, _ = self._build(max_queue_length=3)
        # 头 3 首 OK（每首用独立 grant + 配套 id）
        for i in range(3):
            e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                          requester_id=f"u{i}")
            r = live.queue_request(
                requester_name=f"u{i}", song_id=f"s{i}",
                entitlement_kind=KIND_FAN_JOIN, entitlement_id=e.id,
            )
            self.assertTrue(r.decision.allowed, f"#{i+1} 应允许")
        # 第 4 首拒绝
        e4 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u4")
        with self.assertRaises(LiveServiceError) as ctx:
            live.queue_request(
                requester_name="u4", song_id="s4",
                entitlement_kind=KIND_FAN_JOIN, entitlement_id=e4.id,
            )
        self.assertIn("队列已满", str(ctx.exception))

    def test_per_song_max_actual_blocks_2nd_same_song(self):
        from core.data.live import KIND_FAN_JOIN
        live, ent, _ = self._build(per_song_max_per_session=1)
        e1 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u1")
        e2 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u2")
        # 第 1 首 OK
        r = live.queue_request(
            requester_name="u1", song_id="hot_song",
            entitlement_kind=KIND_FAN_JOIN, entitlement_id=e1.id,
        )
        self.assertTrue(r.decision.allowed)
        # 第 2 首同歌被拒
        with self.assertRaises(LiveServiceError) as ctx:
            live.queue_request(
                requester_name="u2", song_id="hot_song",
                entitlement_kind=KIND_FAN_JOIN, entitlement_id=e2.id,
            )
        self.assertIn("已被点 1 次", str(ctx.exception))

    def test_per_user_max_actual_blocks_2nd_by_same_user(self):
        from core.data.live import KIND_FAN_JOIN
        live, ent, _ = self._build(per_user_max_in_queue=1)
        e1 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u1")
        e2 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u1")
        # 第 1 首 OK
        r = live.queue_request(
            requester_name="u1", requester_id="u1", song_id="s1",
            entitlement_kind=KIND_FAN_JOIN, entitlement_id=e1.id,
        )
        self.assertTrue(r.decision.allowed)
        # 第 2 首同用户不同歌被拒
        with self.assertRaises(LiveServiceError) as ctx:
            live.queue_request(
                requester_name="u1", requester_id="u1", song_id="s2",
                entitlement_kind=KIND_FAN_JOIN, entitlement_id=e2.id,
            )
        self.assertIn("队列里有 1 首", str(ctx.exception))

    def test_cooldown_actual_blocks_immediate_repeat(self):
        """两次入队间隔太短，第二次被拒。"""
        from core.data.live import KIND_FAN_JOIN
        live, ent, _ = self._build(cooldown_seconds_per_user=10)
        e1 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u1")
        e2 = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u1")
        # 第 1 首 OK
        r = live.queue_request(
            requester_name="u1", requester_id="u1", song_id="s1",
            entitlement_kind=KIND_FAN_JOIN, entitlement_id=e1.id,
        )
        self.assertTrue(r.decision.allowed)
        # 立即第二次 → 冷却
        with self.assertRaises(LiveServiceError) as ctx:
            live.queue_request(
                requester_name="u1", requester_id="u1", song_id="s2",
                entitlement_kind=KIND_FAN_JOIN, entitlement_id=e2.id,
            )
        self.assertIn("冷却中", str(ctx.exception))

    def test_manual_add_bypasses_all_conditions(self):
        from core.data.live import KIND_FAN_JOIN
        live, ent, _ = self._build(
            cooldown_seconds_per_user=10,
            max_queue_length=0,
            per_song_max_per_session=1,
            per_user_max_in_queue=1,
        )
        e = ent.grant(kind=KIND_FAN_JOIN, rule_version="rv1", quota=1,
                       requester_id="u")
        # 先用权益占位（同歌同用户各 1 首）
        live.queue_request(
            requester_name="u", requester_id="u", song_id="s1",
            entitlement_kind=KIND_FAN_JOIN, entitlement_id=e.id,
        )
        # 主播手动加同歌应该允许（manual_add 跳过 4 检查）
        r = live.queue_request(
            requester_name="主播", song_id="s1",
            entitlement_kind="manual_add",
        )
        self.assertTrue(r.decision.allowed)

    def test_update_policy_bumps_rule_version(self):
        live, _, _, _ = _build_live()
        old_version = live.session.rule_version
        from core.data.live import RequestPolicy
        new_policy = RequestPolicy(cooldown_seconds_per_user=30)
        result = live.update_policy(new_policy=new_policy)
        self.assertNotEqual(result.rule_version, old_version)
        self.assertEqual(live.session.rule_version, result.rule_version)

    def test_update_policy_same_values_no_bump(self):
        live, _, _, policy = _build_live()
        old_version = live.session.rule_version
        result = live.update_policy(new_policy=policy)
        # 完全相同 → 返回原 policy，不 bump
        self.assertEqual(result.rule_version, old_version)


if __name__ == "__main__":
    unittest.main()
