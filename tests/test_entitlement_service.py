"""R2 P3 EntitlementService 测试——核销幂等性 + 返还 + 账目审计。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.services.entitlements import (
    EntitlementAlreadyConsumed,  # noqa - 用于上层错误捕获
    EntitlementKindUnknown,
    EntitlementService,
    EntitlementServiceError,
)


class EntitlementServiceGrantTests(unittest.TestCase):

    def test_grant_returns_valid_grant(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=3,
                      requester_id="u_1")
        self.assertGreater(len(e.id), 0)
        self.assertEqual(e.remaining(), 3)

    def test_rejects_unknown_kind(self):
        svc = EntitlementService()
        with self.assertRaises(EntitlementKindUnknown):
            svc.grant(kind="lucky", rule_version="rv1", quota=1)

    def test_rejects_zero_quota(self):
        svc = EntitlementService()
        with self.assertRaises(EntitlementServiceError):
            svc.grant(kind="fan_join", rule_version="rv1", quota=0)

    def test_grant_with_evidence(self):
        svc = EntitlementService()
        e = svc.grant(
            kind="gift_exchange", rule_version="rv1", quota=1,
            requester_id="u_1", evidence_label="墨镜", evidence_value=10.0,
            platform_ref="gift_id_xyz",
        )
        self.assertEqual(e.evidence_label, "墨镜")
        self.assertEqual(e.evidence_value, 10.0)


class EntitlementServiceConsumeTests(unittest.TestCase):

    def test_consume_decrements_remaining(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=2,
                      requester_id="u_1")
        r = svc.consume(e.id, command_id="cmd_1")
        self.assertTrue(r.recorded)
        self.assertFalse(r.already_processed)
        self.assertEqual(r.entitlement.remaining(), 1)

    def test_consume_idempotent_same_command_id(self):
        """v3 §6.3: 核销必须幂等，重复提交不能重复扣额度。"""
        svc = EntitlementService()
        e = svc.grant(kind="member_daily", rule_version="rv1", quota=5,
                      requester_id="u_1")
        r1 = svc.consume(e.id, command_id="same-cmd")
        r2 = svc.consume(e.id, command_id="same-cmd")
        self.assertTrue(r2.recorded)
        self.assertTrue(r2.already_processed)
        # 剩余与 r1 一致：3 → 3（只扣一次）
        self.assertEqual(r2.entitlement.remaining(), 4)

    def test_consume_quota_exhausted_rejected(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=1,
                      requester_id="u_1")
        r1 = svc.consume(e.id, command_id="c1")
        self.assertTrue(r1.recorded)
        r2 = svc.consume(e.id, command_id="c2")  # 不同 cmd 也不能
        self.assertFalse(r2.recorded)
        self.assertIn("quota 已用尽", r2.reason)

    def test_consume_missing_entitlement(self):
        svc = EntitlementService()
        r = svc.consume("doesnt_exist", command_id="c1")
        self.assertFalse(r.recorded)
        self.assertIn("不存在", r.reason)

    def test_consume_auto_generates_command_id_when_none(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=3,
                      requester_id="u_1")
        r1 = svc.consume(e.id)
        r2 = svc.consume(e.id)  # 自动生成 cmd，会真扣 2 次
        # 两个独立 consume，扣 2 次
        self.assertEqual(r1.entitlement.remaining(), 2)
        self.assertEqual(r2.entitlement.remaining(), 1)

    def test_ledger_records_each_consumption(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=5,
                      requester_id="u_1")
        svc.consume(e.id, command_id="c1")
        svc.consume(e.id, command_id="c2")
        # 重复 c1 不增加账目
        svc.consume(e.id, command_id="c1")
        # 实际账目应仅含 c1, c2
        cmds = {entry.command_id for entry in svc.ledger()}
        self.assertEqual(cmds, {"c1", "c2"})


class EntitlementServiceRefundTests(unittest.TestCase):

    def test_refund_increments_remaining(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=2,
                      requester_id="u_1")
        svc.consume(e.id, command_id="req_1")
        svc.refund(e.id, command_id="refund:req_1")
        self.assertEqual(svc.get(e.id).remaining(), 2)

    def test_refund_idempotent(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=2,
                      requester_id="u_1")
        svc.consume(e.id, command_id="req_x")
        r1 = svc.refund(e.id, command_id="refund:req_x")
        r2 = svc.refund(e.id, command_id="refund:req_x")
        self.assertTrue(r2.already_processed)
        # 已消耗一次 + 返还一次 → remaining=2 (扣1返1)
        self.assertEqual(svc.get(e.id).remaining(), 2)

    def test_refund_rejects_non_prefixed_command_id(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=1,
                      requester_id="u_1")
        with self.assertRaises(EntitlementServiceError):
            svc.refund(e.id, command_id="wrong_no_prefix")

    def test_refund_when_no_consumed_rejected(self):
        svc = EntitlementService()
        e = svc.grant(kind="fan_join", rule_version="rv1", quota=1,
                      requester_id="u_1")
        r = svc.refund(e.id, command_id="refund:phantom")
        self.assertFalse(r.recorded)
        self.assertIn("返还", r.reason)


class EntitlementServiceLedgerTests(unittest.TestCase):

    def test_ledger_records_audit_trail(self):
        svc = EntitlementService()
        e = svc.grant(kind="campaign", rule_version="rv2", quota=10,
                      requester_id="u_1")
        svc.consume(e.id, command_id="req_a", operator="alice",
                    reason="节日活动")
        entries = svc.ledger()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].operator, "alice")
        self.assertEqual(entries[0].reason, "节日活动")
        self.assertEqual(entries[0].delta, 1)


class EntitlementServiceOperatorAuditTests(unittest.TestCase):

    def test_granted_snapshots_recorded(self):
        """granted() 返回所有已授予权益，便于审计。"""
        svc = EntitlementService()
        svc.grant(kind="member_daily", rule_version="rv1", quota=1)
        svc.grant(kind="fan_join", rule_version="rv1", quota=1)
        grants = svc.granted()
        self.assertEqual(len(grants), 2)
        kinds = {g.kind for g in grants}
        self.assertEqual(kinds, {"member_daily", "fan_join"})


if __name__ == "__main__":
    unittest.main()
