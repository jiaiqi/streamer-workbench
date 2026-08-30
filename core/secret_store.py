"""主密码等秘密信息的跨平台安全存储。

设计目标（来自 2026-08-18 产品与技术优化建议 6.5）：
- macOS → Keychain（系统级）
- Windows → Credential Manager
- Linux → Secret Service

实现策略：
- 优先使用 `keyring` 库（PyPA 官方推荐，跨平台）
- `keyring` 不可用（缺 backend / Keychain 锁定 / OS 不支持）→ 抛 `SecretStoreUnavailable`
  调用方应据此回退为「禁用自动同步」并提示用户
- 绝不写明文或 Base64 编码到 settings.json / 任何持久化文件
- 绝不在网络发送

依赖：
- `keyring>=24`（macOS 自带 backend；Win/Linux 需 `pywin32-ctypes` / `secretstorage`）
- 这是本模块唯一新增的依赖

API：
- `is_available() -> bool`：当前环境是否有可用的后端
- `backend_name() -> str`：当前 backend 的人读名（"macOS Keychain" / "Windows Credential Manager" ...）
- `set_secret(account: str, password: str) -> None`
- `get_secret(account: str) -> str | None`：未设置返 None
- `delete_secret(account: str) -> None`：不存在不报错
- `SecretStoreUnavailable` 异常类
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 单一 service 标识；本项目所有 secret 都用这个 service 区分
SERVICE_NAME = "song-workbench"


class SecretStoreUnavailable(Exception):
    """当前环境无系统 Keychain / Credential Manager / Secret Service。

    评估文档 6.5 明确：系统密钥环不可用时，自动同步默认关闭。
    """


# ── 后端探测 ────────────────────────────────────────────────────────

_available: bool | None = None
_backend_label: str | None = None


def _probe() -> tuple[bool, str]:
    """探测 keyring 是否可用 + 给出可读 backend 名。"""
    global _available, _backend_label
    if _available is not None and _backend_label is not None:
        return _available, _backend_label
    try:
        import keyring  # type: ignore
    except ImportError as exc:
        _available = False
        _backend_label = "keyring 未安装"
        logger.warning("SecretStore: keyring 库未安装 (%s); secret 存储不可用", exc)
        return _available, _backend_label
    try:
        kr = keyring.get_keyring()
        # NullFailure / Fail / Keyring 退化到不可用
        cls_name = kr.__class__.__name__
        # keyring >=24 用 Simple Keyring / NullKeyring 表示不可用
        from keyring.backends.fail import Keyring as FailKeyring  # type: ignore
        from keyring.backends.null import Keyring as NullKeyring  # type: ignore
        if isinstance(kr, (FailKeyring, NullKeyring)):
            _available = False
            _backend_label = f"{cls_name}（无可用 backend）"
            logger.warning("SecretStore: keyring backend = %s; secret 存储不可用", cls_name)
            return _available, _backend_label
        _available = True
        # backend 类名 → 人读名映射
        backend_friendly = {
            "Keyring": "macOS Keychain",  # keyring.backends.macOS.Keyring
            "WinVaultKeyring": "Windows Credential Manager",
            "SecretServiceKeyring": "Linux Secret Service",
            "KWallet": "KDE KWallet",
            "GnomeKeyring": "GNOME Keyring",
        }
        # 尝试从全限定名匹配（如 keyring.backends.macOS.Keyring）
        fq = f"{kr.__class__.__module__}.{kr.__class__.__name__}"
        label = backend_friendly.get(cls_name)
        if label is None and "macOS" in fq:
            label = "macOS Keychain"
        elif label is None and "Windows" in fq:
            label = "Windows Credential Manager"
        elif label is None and "SecretService" in fq:
            label = "Linux Secret Service"
        _backend_label = label or cls_name
        return _available, _backend_label
    except Exception as exc:  # noqa: BLE001
        _available = False
        _backend_label = f"探测失败: {exc}"
        logger.warning("SecretStore: keyring backend 探测失败 (%s)", exc)
        return _available, _backend_label


def is_available() -> bool:
    """当前平台是否有可用的系统密钥环 backend。"""
    return _probe()[0]


def backend_name() -> str:
    """当前 backend 的可读名（用于 UI 展示）。"""
    return _probe()[1]


# ── 核心 API ────────────────────────────────────────────────────────

def set_secret(account: str, password: str) -> None:
    """存密码到系统 Keychain。失败抛 SecretStoreUnavailable。"""
    if not is_available():
        raise SecretStoreUnavailable(f"系统密钥环不可用: {backend_name()}")
    if not account or not isinstance(account, str):
        raise ValueError("account 必须是非空字符串")
    if password is None:
        raise ValueError("password 不能为 None；用 delete_secret 删除")
    try:
        import keyring  # type: ignore
        keyring.set_password(SERVICE_NAME, account, password)
    except Exception as exc:  # noqa: BLE001
        raise SecretStoreUnavailable(
            f"写入系统密钥环失败 ({backend_name()}): {exc}") from exc


def get_secret(account: str) -> Optional[str]:
    """读密码。未设置返 None；backend 不可用抛 SecretStoreUnavailable。"""
    if not is_available():
        raise SecretStoreUnavailable(f"系统密钥环不可用: {backend_name()}")
    if not account or not isinstance(account, str):
        raise ValueError("account 必须是非空字符串")
    try:
        import keyring  # type: ignore
        return keyring.get_password(SERVICE_NAME, account)
    except Exception as exc:  # noqa: BLE001
        raise SecretStoreUnavailable(
            f"读取系统密钥环失败 ({backend_name()}): {exc}") from exc


def delete_secret(account: str) -> None:
    """删密码。不存在不报错；backend 不可用抛 SecretStoreUnavailable。"""
    if not is_available():
        raise SecretStoreUnavailable(f"系统密钥环不可用: {backend_name()}")
    if not account or not isinstance(account, str):
        raise ValueError("account 必须是非空字符串")
    try:
        import keyring  # type: ignore
        from keyring.errors import PasswordDeleteError  # type: ignore
        try:
            keyring.delete_password(SERVICE_NAME, account)
        except PasswordDeleteError:
            # 不存在 — 视为成功（幂等）
            pass
    except SecretStoreUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SecretStoreUnavailable(
            f"删除系统密钥环项失败 ({backend_name()}): {exc}") from exc
