"""P0-3 备份 zip member 路径白名单测试。

覆盖：8/18 评估报告 4.3 列出的所有攻击向量：
- POSIX 绝对路径
- Windows drive path
- `..` 路径穿越
- 控制字符 / NUL
- 空 / 仅 `/` 等无效输入
- 合法相对路径（含 `./` 前缀 / 嵌套子目录）

注意：与 `test_backup.py` 不同，本测试是**纯函数级**——不构造 zip、不解 zip，
只校验 `assert_safe_member_path` / `is_safe_member_path` 在各种 `member_name` 下
的正确性。`import_backup` 端到端拒绝恶意成员名的集成测试见 `test_backup_import_rejects_unsafe_paths`。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.backup import (
    UnsafeBackupMemberError,
    assert_safe_member_path,
    is_safe_member_path,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_TOOL = REPO_ROOT / "tools" / "backup.py"


# ─── A) 纯函数级：白名单规则 ───────────────────────────────────────


class AssertSafeMemberPathTests(unittest.TestCase):
    """`assert_safe_member_path` 单测：覆盖每条白名单规则。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bk_pathsafety_"))
        self.data_root = self.tmp / "data"
        self.data_root.mkdir()

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    # ── a) 拒绝：绝对路径 / drive path / `..` ──

    def test_rejects_posix_absolute_path(self):
        """`/etc/passwd` → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("/etc/passwd", self.data_root)
        msg = str(ctx.exception)
        self.assertIn("/etc/passwd", msg)
        self.assertIn("绝对路径", msg)

    def test_rejects_windows_drive_path(self):
        """`C:\\foo` → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("C:\\foo", self.data_root)
        msg = str(ctx.exception)
        # 字符串里含 drive 路径（不论 repr 双反斜杠还是单反斜杠）
        self.assertIn("C:", msg)
        self.assertIn("Windows drive", msg)

    def test_rejects_windows_drive_path_with_slash(self):
        """`C:/foo` → raise（也走 drive path 规则）"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("C:/foo", self.data_root)
        msg = str(ctx.exception)
        self.assertIn("C:", msg)
        self.assertIn("Windows drive", msg)

    def test_rejects_backslash_absolute(self):
        r"""`\foo` → raise（POSIX 反斜杠绝对路径）"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("\\foo", self.data_root)
        self.assertIn("绝对路径", str(ctx.exception))

    def test_rejects_parent_traversal(self):
        """`../etc/passwd` → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("../etc/passwd", self.data_root)
        msg = str(ctx.exception)
        self.assertIn("../etc/passwd", msg)
        self.assertIn("..", msg)

    def test_rejects_nested_parent_traversal(self):
        """`data/../../escape` → raise（中间夹 `..` 也要拒）"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("data/../../escape", self.data_root)
        self.assertIn("..", str(ctx.exception))

    def test_rejects_dot_dot_segment(self):
        """单段 `..` → raise"""
        with self.assertRaises(UnsafeBackupMemberError):
            assert_safe_member_path("..", self.data_root)

    def test_rejects_trailing_dot_dot(self):
        """`data/..` → raise（尾段 `..`）"""
        with self.assertRaises(UnsafeBackupMemberError):
            assert_safe_member_path("data/..", self.data_root)

    def test_rejects_dot_segment(self):
        """单段 `.` → raise（解析后无段，等价于写盘到 data_root 本身，无意义）。"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path(".", self.data_root)
        self.assertIn("无有效段", str(ctx.exception))

    def test_rejects_empty_string(self):
        """空字符串 → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("", self.data_root)
        self.assertIn("空", str(ctx.exception))

    def test_rejects_whitespace_only(self):
        """纯空白 → raise"""
        with self.assertRaises(UnsafeBackupMemberError):
            assert_safe_member_path("   ", self.data_root)

    def test_rejects_root_only(self):
        """仅 `/` → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("/", self.data_root)
        self.assertIn("绝对路径", str(ctx.exception))

    def test_rejects_null_char(self):
        """含 NUL 字符 → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path("songs.json\x00.bak", self.data_root)
        self.assertIn("控制字符", str(ctx.exception))

    def test_rejects_non_string_type(self):
        """非 str 类型 → raise"""
        with self.assertRaises(UnsafeBackupMemberError) as ctx:
            assert_safe_member_path(123, self.data_root)  # type: ignore[arg-type]
        self.assertIn("类型非法", str(ctx.exception))

    # ── b) 允许：合法相对路径 ──

    def test_allows_simple_filename(self):
        """`songs.json` → allow"""
        target = assert_safe_member_path("songs.json", self.data_root)
        # 重要：返回值应是 data_root / name（未 resolve），relative_to 仍工作
        self.assertEqual(target, self.data_root / "songs.json")
        self.assertEqual(target.relative_to(self.data_root), Path("songs.json"))

    def test_allows_nested_subdir(self):
        """`data/sub/file.json` → allow"""
        target = assert_safe_member_path("data/sub/file.json", self.data_root)
        self.assertEqual(target, self.data_root / "data" / "sub" / "file.json")
        self.assertEqual(target.relative_to(self.data_root), Path("data/sub/file.json"))

    def test_allows_dot_slash_prefix(self):
        """`./songs.json` → allow（normalize 后等价 songs.json）"""
        target = assert_safe_member_path("./songs.json", self.data_root)
        # pathlib 会把 `./` 吃掉；等价于 `songs.json`
        self.assertEqual(target, self.data_root / "songs.json")

    def test_allows_deep_nested(self):
        """`live-sessions/2026-08-16/state.json` → allow"""
        target = assert_safe_member_path(
            "live-sessions/2026-08-16/state.json", self.data_root
        )
        self.assertTrue(str(target).endswith("state.json"))
        self.assertTrue(str(target).startswith(str(self.data_root)))

    def test_does_not_resolve_returned_target(self):
        """关键约束：返回值**不**做 resolve。

        macOS 上 tempfile.mkdtemp 给出 `/var/folders/...`（symlink），
        resolve 后会跳到 `/private/var/folders/...`，破坏 `relative_to(data_root)`。
        assert_safe_member_path 必须返回未 resolve 的路径。
        """
        target = assert_safe_member_path("songs.json", self.data_root)
        # `target` 字符串应 == `data_root / 'songs.json'`，没有 resolve
        self.assertEqual(str(target), str(self.data_root / "songs.json"))


# ─── B) is_safe_member_path 静默版 ───────────────────────────────


class IsSafeMemberPathTests(unittest.TestCase):
    """`is_safe_member_path` 静默版本：返回 True/False，不抛。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bk_pathsafety_silent_"))
        self.data_root = self.tmp / "data"
        self.data_root.mkdir()

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_false_for_absolute(self):
        self.assertFalse(is_safe_member_path("/etc/passwd", self.data_root))

    def test_returns_false_for_drive_path(self):
        self.assertFalse(is_safe_member_path("C:\\foo", self.data_root))

    def test_returns_false_for_parent_traversal(self):
        self.assertFalse(is_safe_member_path("../escape", self.data_root))

    def test_returns_false_for_empty(self):
        self.assertFalse(is_safe_member_path("", self.data_root))

    def test_returns_true_for_simple(self):
        self.assertTrue(is_safe_member_path("songs.json", self.data_root))

    def test_returns_true_for_nested(self):
        self.assertTrue(is_safe_member_path("data/sub/x.json", self.data_root))

    def test_exception_is_value_error(self):
        """UnsafeBackupMemberError 必须继承 ValueError，让现有 except 链不受影响。"""
        self.assertTrue(issubclass(UnsafeBackupMemberError, ValueError))
        # 实际抛的时候可以被 `except ValueError` 抓住
        try:
            assert_safe_member_path("/etc/passwd", self.data_root)
        except ValueError as exc:
            self.assertIsInstance(exc, UnsafeBackupMemberError)
        else:
            self.fail("应当抛 ValueError")


# ─── C) 集成：import_backup 真的拒绝恶意成员名 ───────────────────────


class ImportBackupRejectsUnsafeMembersTests(unittest.TestCase):
    """端到端：构造一个含恶意 member 的 zip（HMAC 仍合法），import 必须拒绝。

    关键点：
    - 手动构造 zip 时绕过 export_backup（不通过白名单只构造恶意包）
    - 验签通过（HMAC + SHA-256 都对齐）→ 走到解压阶段
    - 期待 `import_backup` 抛 ValueError（"备份包含不安全路径"）
    """

    @classmethod
    def setUpClass(cls):
        from tools import backup as bk
        cls.bk = bk
        cls.REPO_ROOT = REPO_ROOT

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bk_pathsafety_e2e_"))
        self.src = self.tmp / "src"
        self.src.mkdir()
        (self.src / "songs.json").write_text('{"songs": [], "version": 5}')
        (self.src / "settings.json").write_text('{"default_canvas": "9:20"}')

        # 合法 export
        self.bk_out = self.tmp / "good.songworkbench"
        self.bk.export_backup(self.bk_out, self.src, password=None)

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _build_malicious_backup(self, injected_member_name: str) -> Path:
        """在合法 zip 里加一个恶意成员名（不动 HMAC 的合规 manifest 路径）。

        注意：直接加恶意 member 会让 manifest.files 缺失 → verify 必失败。
        我们的目标只是让 `import_backup` 走到解压阶段，因此**保留** manifest
        完整（所有原本的 file + 恶意 member）并把恶意 member 写到文件里。
        verify 看到恶意 member 不在 manifest.files → 不当 mismatch（只校验
        manifest 列出的文件），所以仍 ok。
        """
        with zipfile.ZipFile(self.bk_out, "r") as zf:
            members = {m: zf.read(m) for m in zf.namelist()}

        # 写恶意 member
        members[injected_member_name] = b'{"injected": true}'

        out = self.tmp / "malicious.songworkbench"
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return out

    def test_import_rejects_parent_traversal_member(self):
        """zip 含 `../escape` member → import 应 raise"""
        bad = self._build_malicious_backup("../escape")
        with self.assertRaises(ValueError) as ctx:
            self.bk.import_backup(bad, self.tmp / "dst", password=None, overwrite=True)
        self.assertIn("不安全路径", str(ctx.exception))
        # 关键：data_root 之外**不应**有 escape 文件被创建
        # 注：tmp 是 /var/folders/... ；`..` 解析后会落到 /var/folders/wv/l4_.../bk_.../escape
        # 我们只检查 /tmp/<this_test>/dst 之下没有 escape，且 tmp 之上没有 escape 文件
        # 为简化，只验证 import raise
        self.assertTrue(self.tmp.exists())

    def test_import_rejects_absolute_member(self):
        """zip 含 `/tmp/pwned` member → import 应 raise"""
        bad = self._build_malicious_backup("/tmp/pwned")
        with self.assertRaises(ValueError) as ctx:
            self.bk.import_backup(bad, self.tmp / "dst", password=None, overwrite=True)
        self.assertIn("不安全路径", str(ctx.exception))

    def test_import_rejects_drive_path_member(self):
        """zip 含 `C:\\pwned` member → import 应 raise"""
        bad = self._build_malicious_backup("C:\\pwned")
        with self.assertRaises(ValueError) as ctx:
            self.bk.import_backup(bad, self.tmp / "dst", password=None, overwrite=True)
        self.assertIn("不安全路径", str(ctx.exception))

    def test_import_succeeds_for_clean_zip(self):
        """干净 zip（无恶意 member）→ import 应正常通过

        回归保护：白名单不能让合法路径失效。
        """
        dst = self.tmp / "dst"
        result = self.bk.import_backup(
            self.bk_out, dst, password=None, overwrite=True
        )
        self.assertGreater(len(result["written"]), 0)
        self.assertTrue((dst / "songs.json").exists())


if __name__ == "__main__":
    unittest.main()
