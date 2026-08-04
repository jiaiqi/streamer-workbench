"""R2 P3 RequestPolicyService 测试——决策 + 公平保护 + 规则 diff。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.live import (
    PolicyDecision,
    RequestPolicy,
)
from server.services.request_policy import (
    QueueSnapshot,
    RequestPolicyService,
    UnknownEntitlementKind,
)


class RequestPolicyDecideTests(unittest.TestCase):

    def test_default_policy_allowed_for_normal_kinds(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        snap = QueueSnapshot(queue_size=5, current_song_position=1)
        for kind in ("fan_join", "member_daily", "gift_exchange", "campaign"):
            d = svc.decide_queue(entitlement_kind=kind, snapshot=snap)
            self.assertTrue(d.allowed, f"{kind} 应允许")
            self.assertFalse(d.requires_broadcaster_confirmation,
                              f"{kind} 不需主播确认")
            self.assertFalse(d.degraded)

    def test_bump_kind_requires_confirmation(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        snap = QueueSnapshot(queue_size=5, current_song_position=1,
                             recent_bumps_in_a_row=0)
        d = svc.decide_queue(entitlement_kind="manual_bump", snapshot=snap)
        self.assertTrue(d.allowed)
        self.assertTrue(d.requires_broadcaster_confirmation)

    def test_manual_add_does_not_require_confirmation(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        d = svc.decide_queue(entitlement_kind="", snapshot=QueueSnapshot())
        # 主播手动加歌 = 不需要确认
        self.assertTrue(d.allowed)
        self.assertFalse(d.requires_broadcaster_confirmation)

    def test_high_value_gift_unlocks_bump(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        snap = QueueSnapshot(queue_size=8, current_song_position=1)
        d = svc.decide_queue(entitlement_kind="high_value_gift", snapshot=snap)
        self.assertTrue(d.allowed)
        self.assertTrue(d.requires_broadcaster_confirmation)
        # 等价于 manual_bump
        d2 = svc.decide_queue(entitlement_kind="manual_bump", snapshot=snap)
        self.assertEqual(d2.requires_broadcaster_confirmation,
                         d.requires_broadcaster_confirmation)

    def test_missing_kind_defaults_to_manual_add(self):
        """entitlement_kind="" 视为主播直接加歌 (manual)，允许不入队。"""
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        d = svc.decide_queue(entitlement_kind="", snapshot=QueueSnapshot())
        self.assertTrue(d.allowed)
        # 不需要主播确认（主插自己加）
        self.assertFalse(d.requires_broadcaster_confirmation)

    def test_unknown_kind_raises(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        with self.assertRaises(UnknownEntitlementKind):
            svc.decide_queue(entitlement_kind="lucky", snapshot=QueueSnapshot())

    def test_fairness_protection_triggers_degraded(self):
        """v3 §6.4 公平保护：连续插队达到上限后，需要说明原因。"""
        policy = RequestPolicy(rule_version="rv1",
                                fairness_max_consecutive_bumps=3)
        svc = RequestPolicyService(policy=policy)
        # 连续 3 次后立即触发
        snap = QueueSnapshot(queue_size=15, current_song_position=1,
                             recent_bumps_in_a_row=3)
        d = svc.decide_queue(entitlement_kind="manual_bump", snapshot=snap)
        self.assertTrue(d.allowed)
        self.assertTrue(d.requires_broadcaster_confirmation)
        self.assertTrue(d.degraded)
        self.assertIn("插队上限", d.reason)

    def test_fairness_off_when_under_threshold(self):
        policy = RequestPolicy(rule_version="rv1",
                                fairness_max_consecutive_bumps=3)
        svc = RequestPolicyService(policy=policy)
        snap = QueueSnapshot(recent_bumps_in_a_row=2)
        d = svc.decide_queue(entitlement_kind="manual_bump", snapshot=snap)
        self.assertFalse(d.degraded)


class BumpPositionTests(unittest.TestCase):

    def test_default_position_is_current_plus_bump_target(self):
        policy = RequestPolicy(rule_version="rv1", bump_default_target=3)
        svc = RequestPolicyService(policy=policy)
        pos = svc.decide_bump_position(QueueSnapshot(current_song_position=1))
        self.assertEqual(pos, 4)

    def test_bump_target_propagates(self):
        policy = RequestPolicy(rule_version="rv1", bump_default_target=5)
        svc = RequestPolicyService(policy=policy)
        pos = svc.decide_bump_position(QueueSnapshot(current_song_position=2))
        self.assertEqual(pos, 7)


class RuleDiffTests(unittest.TestCase):

    def test_same_rules_no_diff(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        new_p = RequestPolicy(rule_version="rv2")  # 不同 version 但同字段
        self.assertFalse(svc.rule_differs(new_p))

    def test_quota_change_differs(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        new_p = RequestPolicy(rule_version="rv2", fan_join_session_quota=2)
        self.assertTrue(svc.rule_differs(new_p))

    def test_fairness_change_differs(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rv1"))
        new_p = RequestPolicy(rule_version="rv2", fairness_max_consecutive_bumps=5)
        self.assertTrue(svc.rule_differs(new_p))


class RuleVersionReportingTests(unittest.TestCase):

    def test_rule_version_kept(self):
        svc = RequestPolicyService(policy=RequestPolicy(rule_version="rule_42"))
        self.assertEqual(svc.rule_version, "rule_42")
        # decide 不修改它
        d = svc.decide_queue(entitlement_kind="fan_join",
                              snapshot=QueueSnapshot())
        self.assertEqual(d.rule_version, "rule_42")


# ── M2.4 点歌条件 ──


class M24QueueLimitTests(unittest.TestCase):
    def setUp(self):
        from dataclasses import replace
        from core.data.live import RequestPolicy
        self._replace = replace
        self._RequestPolicy = RequestPolicy

    def test_max_queue_length_blocks_when_full(self):
        policy = self._RequestPolicy(max_queue_length=3)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(queue_size=3),
        )
        self.assertFalse(d.allowed)
        self.assertIn("队列已满", d.reason)

    def test_max_queue_length_zero_unlimited(self):
        policy = self._RequestPolicy(max_queue_length=0)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(queue_size=999),
        )
        self.assertTrue(d.allowed)

    def test_max_queue_length_under_limit_allows(self):
        policy = self._RequestPolicy(max_queue_length=10)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(queue_size=5),
        )
        self.assertTrue(d.allowed)


class M24PerSongLimitTests(unittest.TestCase):
    def test_per_song_max_blocks_at_limit(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(per_song_max_per_session=2)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(per_song_in_session=2),
        )
        self.assertFalse(d.allowed)
        self.assertIn("已被点 2 次", d.reason)

    def test_per_song_max_zero_unlimited(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(per_song_max_per_session=0)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(per_song_in_session=999),
        )
        self.assertTrue(d.allowed)


class M24PerUserLimitTests(unittest.TestCase):
    def test_per_user_max_blocks_at_limit(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(per_user_max_in_queue=2)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(per_user_in_queue=2),
        )
        self.assertFalse(d.allowed)
        self.assertIn("队列里有 2 首", d.reason)

    def test_per_user_max_under_limit_allows(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(per_user_max_in_queue=5)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(per_user_in_queue=2),
        )
        self.assertTrue(d.allowed)


class M24CooldownTests(unittest.TestCase):
    def test_cooldown_blocks_when_elapsed_under_threshold(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(cooldown_seconds_per_user=10)
        svc = RequestPolicyService(policy=policy)
        # 上次入队 3 秒前 → 还在冷却
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(cooldown_seconds_remaining=3.0),
        )
        self.assertFalse(d.allowed)
        self.assertIn("冷却中", d.reason)
        self.assertIn("7", d.reason)  # 10-3=7

    def test_cooldown_allows_when_elapsed_exceeds_threshold(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(cooldown_seconds_per_user=10)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(cooldown_seconds_remaining=15.0),
        )
        self.assertTrue(d.allowed)

    def test_cooldown_zero_unlimited(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(cooldown_seconds_per_user=0)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(cooldown_seconds_remaining=0.0),
        )
        self.assertTrue(d.allowed)

    def test_cooldown_none_means_no_history_allows(self):
        """第一次入队（无历史）→ 允许。"""
        from core.data.live import RequestPolicy
        policy = RequestPolicy(cooldown_seconds_per_user=10)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="fan_join",
            snapshot=QueueSnapshot(cooldown_seconds_remaining=None),
        )
        self.assertTrue(d.allowed)


class M24ManualAddBypassesTests(unittest.TestCase):
    def test_manual_add_skips_all_4_checks(self):
        from core.data.live import RequestPolicy
        policy = RequestPolicy(
            cooldown_seconds_per_user=10,
            max_queue_length=1,
            per_song_max_per_session=1,
            per_user_max_in_queue=1,
        )
        svc = RequestPolicyService(policy=policy)
        # 即使所有条件都超限，manual_add 必须允许
        d = svc.decide_queue(
            entitlement_kind="manual_add",
            snapshot=QueueSnapshot(
                queue_size=999,
                cooldown_seconds_remaining=0.0,
                per_song_in_session=999,
                per_user_in_queue=999,
            ),
        )
        self.assertTrue(d.allowed)

    def test_bump_kind_still_goes_through_4_checks(self):
        """high_value_gift / manual_bump 走 M2.4 检查 → 防止刷榜。"""
        from core.data.live import RequestPolicy
        policy = RequestPolicy(max_queue_length=1)
        svc = RequestPolicyService(policy=policy)
        d = svc.decide_queue(
            entitlement_kind="high_value_gift",
            snapshot=QueueSnapshot(queue_size=1),
        )
        self.assertFalse(d.allowed)


class M24RuleDiffersTests(unittest.TestCase):
    def test_differs_on_cooldown_change(self):
        from core.data.live import RequestPolicy
        a = RequestPolicy(cooldown_seconds_per_user=0)
        b = RequestPolicy(cooldown_seconds_per_user=10)
        self.assertTrue(RequestPolicyService(policy=a).rule_differs(b))

    def test_differs_on_max_queue_change(self):
        from core.data.live import RequestPolicy
        a = RequestPolicy(max_queue_length=0)
        b = RequestPolicy(max_queue_length=20)
        self.assertTrue(RequestPolicyService(policy=a).rule_differs(b))

    def test_not_differs_on_zero_change(self):
        from core.data.live import RequestPolicy
        a = RequestPolicy()
        b = RequestPolicy(rule_version="rule_diff")
        self.assertFalse(RequestPolicyService(policy=a).rule_differs(b))


class M24ValidateTests(unittest.TestCase):
    def test_negative_cooldown_rejected(self):
        from core.data.live import RequestPolicy
        with self.assertRaises(ValueError):
            RequestPolicy(cooldown_seconds_per_user=-1).validate()

    def test_zero_values_all_valid(self):
        from core.data.live import RequestPolicy
        RequestPolicy(
            cooldown_seconds_per_user=0,
            max_queue_length=0,
            per_song_max_per_session=0,
            per_user_max_in_queue=0,
        ).validate()  # 不抛


if __name__ == "__main__":
    unittest.main()
