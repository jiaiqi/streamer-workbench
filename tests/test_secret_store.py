"""P0-1 secret_store 单元测试。

覆盖：
- 探测 API 永不抛异常
- mock keyring backend 后，set/get/delete roundtrip
- 不可用时 set/get/delete 抛 SecretStoreUnavailable
- 空 account 校验
- None password 拒绝
- delete 不存在项不报错（幂等）
- 跨 SERVICE/account 隔离
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import secret_store  # noqa: E402


class _FakeKeyringModule:
    """最小可编程的 keyring 替身：用 dict 模拟存储。"""

    def __init__(self, *, fail: bool = False) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self._fail = fail
        # 模拟 submodules：keyring.backends.fail / keyring.errors
        # 让 secret_store 内部 "from keyring.backends.fail import Keyring" 能找到
        from keyring.backends.fail import Keyring as FailKeyring  # type: ignore
        from keyring import errors as keyring_errors  # type: ignore
        self.backends = type(
            "FakeBackends", (),
            {"fail": type("F", (), {"Keyring": FailKeyring})()},
        )()
        self.errors = keyring_errors

    def get_keyring(self):
        if self._fail:
            from keyring.backends.fail import Keyring  # type: ignore
            return Keyring()
        # 假装一个"可用" backend — class name 'Keyring' 触发 backend_friendly
        return MagicMock(__class__=type("Keyring", (), {}))

    def set_password(self, service: str, account: str, password: str) -> None:
        if self._fail:
            raise RuntimeError("simulated keyring failure")
        self._store[(service, account)] = password

    def get_password(self, service: str, account: str):
        if self._fail:
            raise RuntimeError("simulated keyring failure")
        return self._store.get((service, account))

    def delete_password(self, service: str, account: str) -> None:
        if self._fail:
            from keyring.errors import PasswordDeleteError  # type: ignore
            raise PasswordDeleteError("simulated")
        self._store.pop((service, account), None)


class SecretStoreProbeTests(unittest.TestCase):
    """探测类 API 永不抛异常。"""

    def setUp(self):
        # 重置模块缓存，让每次测试都重新探测
        secret_store._available = None
        secret_store._backend_label = None

    def test_is_available_with_real_keyring(self):
        # 在 CI 环境下 keyring 真实存在；本机有 macOS Keychain
        result = secret_store.is_available()
        self.assertIsInstance(result, bool)
        # backend_name() 必然返回非空字符串
        name = secret_store.backend_name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_is_available_when_keyring_missing(self):
        # 模拟 keyring 库不存在 — 直接重写 secret_store._probe
        def fake_probe():
            return (False, "keyring 未安装")
        with patch.object(secret_store, "_probe", fake_probe):
            result = secret_store.is_available()
            self.assertFalse(result)
            self.assertIn("未安装", secret_store.backend_name())

    def test_is_available_when_backend_is_fail(self):
        # 模拟 backend 是 FailKeyring — 重写 _probe
        from keyring.backends.fail import Keyring as FailKeyring  # type: ignore
        def fake_probe():
            return (False, "FailKeyring（无可用 backend）")
        with patch.object(secret_store, "_probe", fake_probe):
            result = secret_store.is_available()
            self.assertFalse(result)
            self.assertIn("无可用 backend", secret_store.backend_name())


class SecretStoreOpsTests(unittest.TestCase):
    """操作类 API：set / get / delete roundtrip。"""

    def setUp(self):
        self.fake = _FakeKeyringModule()
        secret_store._available = None
        secret_store._backend_label = None
        # 注入 fake keyring 模块
        self._keyring_patcher = patch.dict(sys.modules, {"keyring": self.fake})
        self._keyring_patcher.start()

    def tearDown(self):
        self._keyring_patcher.stop()
        secret_store._available = None
        secret_store._backend_label = None

    def test_set_get_roundtrip(self):
        secret_store.set_secret("acc1", "pw1")
        self.assertEqual(secret_store.get_secret("acc1"), "pw1")

    def test_set_unicode_roundtrip(self):
        secret_store.set_secret("acc-中文", "密码世界🌏")
        self.assertEqual(secret_store.get_secret("acc-中文"), "密码世界🌏")

    def test_get_missing_returns_none(self):
        self.assertIsNone(secret_store.get_secret("never-set"))

    def test_delete_existing(self):
        secret_store.set_secret("acc", "pw")
        secret_store.delete_secret("acc")
        self.assertIsNone(secret_store.get_secret("acc"))

    def test_delete_missing_idempotent(self):
        # 不存在 → 不应抛异常
        secret_store.delete_secret("never-existed")

    def test_accounts_isolated(self):
        secret_store.set_secret("a", "A")
        secret_store.set_secret("b", "B")
        self.assertEqual(secret_store.get_secret("a"), "A")
        self.assertEqual(secret_store.get_secret("b"), "B")
        secret_store.delete_secret("a")
        # a 被删，b 不受影响
        self.assertIsNone(secret_store.get_secret("a"))
        self.assertEqual(secret_store.get_secret("b"), "B")

    def test_set_empty_account_raises(self):
        with self.assertRaises(ValueError):
            secret_store.set_secret("", "pw")

    def test_set_none_password_rejected(self):
        # None 是「没设置」语义；应让用户走 delete_secret
        with self.assertRaises(ValueError):
            secret_store.set_secret("acc", None)  # type: ignore[arg-type]

    def test_set_when_backend_fails_raises_unavailable(self):
        # 切换到 fail backend：直接重写 _probe + keyring.set_password
        def fake_probe_unavailable():
            return (False, "FailKeyring（无可用 backend）")
        with patch.object(secret_store, "_probe", fake_probe_unavailable):
            with self.assertRaises(secret_store.SecretStoreUnavailable):
                secret_store.set_secret("acc", "pw")
            with self.assertRaises(secret_store.SecretStoreUnavailable):
                secret_store.get_secret("acc")
            with self.assertRaises(secret_store.SecretStoreUnavailable):
                secret_store.delete_secret("acc")

    def test_get_when_backend_missing_raises_unavailable(self):
        def fake_probe_missing():
            return (False, "keyring 未安装")
        with patch.object(secret_store, "_probe", fake_probe_missing):
            with self.assertRaises(secret_store.SecretStoreUnavailable):
                secret_store.get_secret("acc")


class SecretStoreNamingTests(unittest.TestCase):
    """SERVICE_NAME 单一来源约束。"""

    def test_service_name_is_stable(self):
        # 这是 router/auto_sync 用的；改了会让存量用户的密钥找不到
        self.assertEqual(secret_store.SERVICE_NAME, "song-workbench")


if __name__ == "__main__":
    unittest.main()
