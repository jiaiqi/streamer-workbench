"""P0-3：备份路径安全 + 备份 IO 工具。

子模块：
- `path_safety`: 备份 zip member 路径白名单校验（绝对/穿越/drive path 拒绝）

设计：
- 本包只放与「安全/白名单/边界 IO」相关的纯函数工具，
  渲染 / 网络 / UI 全部解耦，可被 tools/backup.py / core/webdav.py / 服务层复用
- 不 import 任何 UI/服务框架（遵 AGENTS.md 铁律 2）
"""
from __future__ import annotations

from core.backup.path_safety import (
    UnsafeBackupMemberError,
    assert_safe_member_path,
    is_safe_member_path,
)

__all__ = [
    "UnsafeBackupMemberError",
    "assert_safe_member_path",
    "is_safe_member_path",
]
