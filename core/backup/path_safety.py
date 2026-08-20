"""P0-3：备份 zip member 路径安全校验。

攻击面（8/18 评估报告 4.3）：
- `tools/backup.py:import_backup` 之前把 zip member name 直接拼到 data_root 上写盘，
  没有路径白名单，恶意包可写绝对路径 / `..` 穿越 / Windows drive path。

安全策略：
- 拒绝空字符串 / 仅 `/` / 仅 `..` 等无效成员名
- 拒绝 POSIX 绝对路径（以 `/` 开头）
- 拒绝 Windows 绝对路径（盘符如 ``C:\\`` / ``C:/``）
- 拒绝任何含 `..` 路径段（含首段、含中段、含尾段）
- resolve 后必须仍在 `data_root.resolve()` 之内（用 `is_relative_to` 守门）
- 拒绝 NUL 字符 / 控制字符（防 zip 实现边界差异）

本模块仅依赖 stdlib（`pathlib`），与渲染/网络/UI 完全解耦，可被
`tools/backup.py` / `core/webdav.py` / 未来 CLI 复用。

异常：
- `UnsafeBackupMemberError(ValueError)`：继承 ValueError 让现有
  `try/except ValueError` 链不受影响；消息含原始 `member_name` 和具体
  reason，便于定位恶意包。

典型用法：
    from core.backup.path_safety import assert_safe_member_path
    try:
        target = assert_safe_member_path(member_name, data_root)
    except UnsafeBackupMemberError as exc:
        raise ValueError(f"恶意备份条目: {exc}") from exc
    target.write_bytes(zf.read(member_name))
"""
from __future__ import annotations

import re
from pathlib import Path


# 异常类型 ──────────────────────────────────────────────


class UnsafeBackupMemberError(ValueError):
    """备份 zip 内的某个 member 路径不安全（绝对 / 穿越 / drive path 等）。

    继承 ValueError 让现有 `except ValueError` 链不受影响。
    消息必须包含原始 `member_name` + 具体 reason，便于定位恶意包。
    """


# 路径解析小工具 ────────────────────────────────────────


# Windows drive path：单字母 + 冒号 + 分隔符（`C:\` / `C:/`）。
# 在 POSIX 上冒号也是合法文件名一部分，但作为「绝对路径」检测时仍按 win 风格处理，
# 因为备份跨平台语义：win 客户端生成 → posix 客户端导入也必须拒绝。
_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

# 拒绝 NUL 与其他 ASCII 控制字符（< 0x20）—— 各种 zip 实现的边界
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


# 公共 API ─────────────────────────────────────────────


def is_safe_member_path(member_name: str, data_root: Path) -> bool:
    """静默版：返回 True/False，不抛异常。

    用于只想知道"这个名能不能用"的场景（如做预校验 / 报告统计）。
    真正的写盘路径请用 `assert_safe_member_path`。
    """
    try:
        assert_safe_member_path(member_name, data_root)
        return True
    except UnsafeBackupMemberError:
        return False


def assert_safe_member_path(member_name: str, data_root: Path) -> Path:
    """校验 zip member 路径安全，返回 `data_root / member_name` 的拼接路径。

    安全规则（全部必须通过才放行）：
    a) 非空 / 非纯分隔符 / 非 `..` 单段
    b) 非 POSIX 绝对路径（不以 `/` 开头）
    c) 非 Windows drive path（`C:\\` / `C:/`）
    d) 不含 `..` 路径段
    e) 不含 NUL / 控制字符
    f) resolve 后必须仍在 `data_root.resolve()` 之内（`is_relative_to` 守门）

    关于返回值：
    - 严格等价于 `Path(data_root) / member_name`，**不**对 target 做 resolve。
      这样调用方仍可 `target.relative_to(data_root)` 取回原 `member_name`，
      不会因为 macOS 上 `/var/folders/...` 软链被 resolve 到 `/private/var/folders/...`
      而破坏现有 `written` 列表 / 既有测试期望。
    - 安全检查用 `data_root.resolve()` + `target.resolve()` 内部的局部变量完成。

    Args:
        member_name: zip 内的成员名（原始字符串，含正反斜杠）
        data_root: 备份根目录（目标）

    Returns:
        `data_root / member_name` 拼接后的 Path（未 resolve）

    Raises:
        UnsafeBackupMemberError: 任一规则不通过；消息含原始 `member_name` 和 reason
    """
    # 1) 类型 / 空值
    if not isinstance(member_name, str):
        raise UnsafeBackupMemberError(
            f"拒绝: 成员名类型非法 ({type(member_name).__name__}): {member_name!r}"
        )
    if not member_name or not member_name.strip():
        raise UnsafeBackupMemberError(f"拒绝: 成员名为空: {member_name!r}")

    # 2) 控制字符 / NUL
    if _CONTROL_CHAR_RE.search(member_name):
        raise UnsafeBackupMemberError(
            f"拒绝: 成员名含控制字符 / NUL: {member_name!r}"
        )

    # 3) Windows drive path（顺序在 POSIX 绝对路径之前，避免 `C:\foo` 误判）
    if _DRIVE_PATH_RE.match(member_name):
        raise UnsafeBackupMemberError(
            f"拒绝: 成员名是 Windows drive 绝对路径: {member_name!r}"
        )

    # 4) POSIX 绝对路径
    if member_name.startswith("/") or member_name.startswith("\\"):
        raise UnsafeBackupMemberError(
            f"拒绝: 成员名是绝对路径: {member_name!r}"
        )

    # 5) 路径段中不能含 `..`
    # 注意：纯 `..` 段必须先单独拒绝（否则 `..` 作为 `Path.parts` 一段也可被探出，
    # 但 `Path('..') == Path('.')` 这种边界可能绕过，纯 `..`/`.` 显式拒）
    parts = Path(member_name).parts
    if not parts:
        # 空 / `.` 这种「解析后无段」的情形：等价于根目录或当前目录，
        # 不是路径穿越，但写盘后毫无意义 → 拒
        raise UnsafeBackupMemberError(
            f"拒绝: 成员名解析后无有效段: {member_name!r}"
        )
    for seg in parts:
        if seg in ("..", ""):
            raise UnsafeBackupMemberError(
                f"拒绝: 成员名含 `..` / 空段（路径穿越）: {member_name!r}"
            )

    # 6) resolve 后必须在 data_root 之内（仅做安全检查，不修改返回值）
    #    macOS / Linux 上 `/var/folders/...` 实际是 `/private/var/folders/...` 软链；
    #    这里用 resolve 来发现「逃出 data_root」的越界，但**不**把 resolve 后的路径
    #    返回给调用方（避免破坏 `relative_to(data_root)` 行为）。
    try:
        root_resolved = Path(data_root).resolve()
    except OSError as exc:
        raise UnsafeBackupMemberError(
            f"拒绝: data_root 无法 resolve ({data_root!r}): {exc}"
        ) from exc
    try:
        target_resolved = (Path(data_root) / member_name).resolve()
    except OSError as exc:
        raise UnsafeBackupMemberError(
            f"拒绝: 目标路径无法 resolve ({member_name!r}): {exc}"
        ) from exc

    # is_relative_to 兼容 Py 3.9+，本项目最低 3.12
    if not target_resolved.is_relative_to(root_resolved):
        raise UnsafeBackupMemberError(
            f"拒绝: 解析后路径逃出 data_root: member={member_name!r} "
            f"target={str(target_resolved)!r} data_root={str(root_resolved)!r}"
        )

    # 返回**未 resolve**的拼接路径，保留调用方的 `relative_to(data_root)` 行为
    return Path(data_root) / member_name


__all__ = [
    "UnsafeBackupMemberError",
    "assert_safe_member_path",
    "is_safe_member_path",
]
