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


if __name__ == "__main__":
    unittest.main()
