"""R2 P3 直播领域类型测试。

覆盖：6 个 dataclass 的 validate + frozen 不可变 + 状态机白名单。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.live import (
    EntitlementGrant,
    KIND_CAMPAIGN,
    KIND_FAN_JOIN,
    KIND_GIFT_EXCHANGE,
    KIND_MANUAL,
    KIND_MEMBER_DAILY,
    LiveSession,
    PerformanceRecord,
    PolicyDecision,
    QueueEntry,
    RequestPolicy,
    RESULT_CANCELLED,
    RESULT_CURRENT,
    RESULT_DUPLICATE_MERGED,
    RESULT_PENDING,
    RESULT_POSTPONED,
    RESULT_QUEUED,
    RESULT_REQUESTED,
    RESULT_SKIPPED,
    RESULT_SUNG,
    RESULT_UNKNOWN,
    SESSION_ACTIVE,
    SESSION_CLOSED,
    SongRequest,
    VALID_RESULT_STATES,
)


class _Ids:
    """最小化合法身份 fixture。"""
    SESSION = "live_test_1"
    SONG = "song_227fe9c4775f51e2a3e414bc78fdf12e"
    USER = "user_test_1"


class SongRequestTests(unittest.TestCase):

    def test_default_fails_without_requester(self):
        with self.assertRaises(ValueError):
            SongRequest().validate()

    def test_requires_at_least_one_requester(self):
        # 只有 requester_name 应通过
        SongRequest(requester_name="张三", song_id=_Ids.SONG,
                    session_id=_Ids.SESSION).validate()
        # 只有 requester_id 应通过
        SongRequest(requester_id="u_1", song_id=_Ids.SONG,
                    session_id=_Ids.SESSION).validate()

    def test_rejects_blank_name_without_id(self):
        with self.assertRaises(ValueError):
            SongRequest(requester_name="   ",
                        song_id=_Ids.SONG, session_id=_Ids.SESSION).validate()

    def test_rejects_missing_song_id(self):
        with self.assertRaises(ValueError):
            SongRequest(requester_id="u_1", session_id=_Ids.SESSION).validate()

    def test_rejects_entitlement_kind_without_id(self):
        """entitlement_kind 必须配套 entitlement_id（防止孤儿）。"""
        with self.assertRaises(ValueError):
            SongRequest(requester_id="u_1", song_id=_Ids.SONG,
                        session_id=_Ids.SESSION,
                        entitlement_kind=KIND_FAN_JOIN).validate()

    def test_valid_with_entitlement_pair(self):
        SongRequest(requester_id="u_1", song_id=_Ids.SONG,
                    session_id=_Ids.SESSION,
                    entitlement_kind=KIND_FAN_JOIN,
                    entitlement_id="ent_1").validate()


class QueueEntryTests(unittest.TestCase):

    def test_valid_queued(self):
        q = QueueEntry(request_id="r_1", session_id=_Ids.SESSION,
                       song_id=_Ids.SONG, position=1,
                       state=RESULT_QUEUED, requester_name="张三")
        q.validate()

    def test_rejects_negative_position(self):
        q = QueueEntry(request_id="r_1", session_id=_Ids.SESSION,
                       song_id=_Ids.SONG, position=-1)
        with self.assertRaises(ValueError):
            q.validate()

    def test_rejects_unknown_state(self):
        q = QueueEntry(request_id="r_1", session_id=_Ids.SESSION,
                       song_id=_Ids.SONG, position=1, state="lucky")
        with self.assertRaises(ValueError):
            q.validate()

    def test_bumped_requires_original_position(self):
        q = QueueEntry(request_id="r_1", session_id=_Ids.SESSION,
                       song_id=_Ids.SONG, position=1,
                       is_bumped=True, bump_reason="插队")
        with self.assertRaises(ValueError):
            q.validate()


class PerformanceRecordTests(unittest.TestCase):

    def test_sung_requires_performed_at(self):
        p = PerformanceRecord(request_id="r_1", session_id=_Ids.SESSION,
                              song_id=_Ids.SONG, result=RESULT_SUNG)
        with self.assertRaises(ValueError):
            p.validate()

    def test_skipped_ok_without_performed_at(self):
        p = PerformanceRecord(request_id="r_1", session_id=_Ids.SESSION,
                              song_id=_Ids.SONG, result=RESULT_SKIPPED,
                              reason="时间不足")
        p.validate()

    def test_rejects_result_outside_whitelist(self):
        p = PerformanceRecord(request_id="r_1", session_id=_Ids.SESSION,
                              song_id=_Ids.SONG, result="lucky")
        with self.assertRaises(ValueError):
            p.validate()


class RequestPolicyTests(unittest.TestCase):

    def test_default_validates(self):
        RequestPolicy().validate()

    def test_rejects_zero_quota(self):
        rp = RequestPolicy(fan_join_session_quota=0)
        with self.assertRaises(ValueError):
            rp.validate()

    def test_rejects_zero_bump_default(self):
        rp = RequestPolicy(bump_default_target=0)
        with self.assertRaises(ValueError):
            rp.validate()

    def test_rejects_zero_fairness(self):
        rp = RequestPolicy(fairness_max_consecutive_bumps=0)
        with self.assertRaises(ValueError):
            rp.validate()

    def test_rule_version_required(self):
        rp = RequestPolicy(rule_version="")
        with self.assertRaises(ValueError):
            rp.validate()


class EntitlementGrantTests(unittest.TestCase):

    def test_remaining_decrements_with_consumed(self):
        e = EntitlementGrant(rule_version="r1", kind=KIND_FAN_JOIN, quota=3)
        self.assertEqual(e.remaining(), 3)
        e2 = EntitlementGrant(rule_version="r1", kind=KIND_FAN_JOIN, quota=3, consumed=2)
        self.assertEqual(e2.remaining(), 1)

    def test_consumed_cannot_exceed_quota(self):
        e = EntitlementGrant(rule_version="r1", kind=KIND_FAN_JOIN,
                            quota=1, consumed=2)
        with self.assertRaises(ValueError):
            e.validate()

    def test_negative_consumed_rejected(self):
        e = EntitlementGrant(rule_version="r1", kind=KIND_FAN_JOIN,
                            quota=1, consumed=-1)
        with self.assertRaises(ValueError):
            e.validate()

    def test_unknown_kind_rejected(self):
        e = EntitlementGrant(rule_version="r1", kind="lucky", quota=1)
        with self.assertRaises(ValueError):
            e.validate()

    def test_all_documented_kinds_accepted(self):
        for kind in (KIND_FAN_JOIN, KIND_MEMBER_DAILY, KIND_GIFT_EXCHANGE,
                     KIND_CAMPAIGN, KIND_MANUAL):
            EntitlementGrant(rule_version="r1", kind=kind, quota=1).validate()

    def test_frozen_blocks_direct_consumed_assign(self):
        """frozen dataclass 必须用 replace(...) 创建新实例。"""
        import dataclasses
        e = EntitlementGrant(rule_version="r1", kind=KIND_FAN_JOIN, quota=1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.consumed = 1  # type: ignore[misc]


class LiveSessionTests(unittest.TestCase):

    def test_valid_active_session(self):
        LiveSession(rule_version="r1").validate()

    def test_active_without_rule_version_rejected(self):
        with self.assertRaises(ValueError):
            LiveSession().validate()

    def test_closed_requires_closed_at(self):
        s = LiveSession(state=SESSION_CLOSED, rule_version="r1")
        with self.assertRaises(ValueError):
            s.validate()  # 默认 closed_at=None
        # 有 closed_at 应通过
        LiveSession(state=SESSION_CLOSED, rule_version="r1",
                    closed_at="2026-07-30T12:00:00+08:00").validate()

    def test_valid_closed_with_closed_at(self):
        """forward 验证 closed + closed_at 同时给齐。"""
        LiveSession(state=SESSION_CLOSED, rule_version="r1",
                    closed_at="2026-07-30T12:00:00+08:00").validate()

    def test_valid_closed_with_closed_at(self):
        LiveSession(state=SESSION_CLOSED, rule_version="r1",
                    closed_at="2026-07-30T12:00:00+08:00").validate()


class PolicyDecisionTests(unittest.TestCase):

    def test_allowed_constructs(self):
        d = PolicyDecision(allowed=True, entitlement_id="e_1",
                           rule_version="r1")
        self.assertTrue(d.allowed)
        self.assertFalse(d.degraded)

    def test_bumped_requires_confirmation(self):
        d = PolicyDecision(allowed=True, requires_broadcaster_confirmation=True,
                           rule_version="r1")
        self.assertTrue(d.requires_broadcaster_confirmation)


class ValidResultStatesContractTests(unittest.TestCase):
    """对照 v3 §6.5 状态机白名单。"""

    def test_all_documented_states_in_whitelist(self):
        expected = {
            RESULT_PENDING, RESULT_REQUESTED, RESULT_QUEUED, RESULT_CURRENT,
            RESULT_SUNG, RESULT_POSTPONED, RESULT_UNKNOWN, RESULT_SKIPPED,
            RESULT_CANCELLED, RESULT_DUPLICATE_MERGED,
        }
        self.assertEqual(expected, VALID_RESULT_STATES)


if __name__ == "__main__":
    unittest.main()
