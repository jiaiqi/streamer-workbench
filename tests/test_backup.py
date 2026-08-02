"""M0.4 蓝图 v0.1：加密备份包 MVP 测试。

覆盖：export / verify / list / import / HMAC 校验 / 密码错误拒绝 / 快照自动创建。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_TOOL = REPO_ROOT / "tools" / "backup.py"

# 临时测试目录
_TMP = Path(tempfile.mkdtemp(prefix="backup_test_"))


def setUpModule():
    """复制 data/ 到临时目录，避免污染源数据。"""
    src = REPO_ROOT / "data"
    if not src.exists():
        raise RuntimeError(f"源 data 目录不存在: {src}")
    shutil.copytree(src, _TMP / "data_src")
    shutil.copytree(src, _TMP / "data_dst")


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


def _run_backup(*args: str) -> tuple[int, str, str]:
    """调 tools/backup.py 子进程，返回 (returncode, stdout, stderr)。"""
    import subprocess
    proc = subprocess.run(
        ["python3", str(BACKUP_TOOL), *args],
        capture_output=True, text=True, env={"PYTHONPATH": str(REPO_ROOT)},
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_backup_inprocess(*args: str) -> tuple[int, str]:
    """同进程调 backup 模块（导入 + 调函数），更快。"""
    from tools import backup as bk
    cmd = args[0]
    out_path = None
    in_path = None
    data_root = None
    password = None
    overwrite = False
    i = 1
    while i < len(args):
        if args[i] in ("--output", "-o"):
            out_path = Path(args[i + 1]); i += 2
        elif args[i] in ("--input", "-i"):
            in_path = Path(args[i + 1]); i += 2
        elif args[i] == "--data-root":
            data_root = Path(args[i + 1]); i += 2
        elif args[i] == "--password":
            password = args[i + 1]; i += 2
        elif args[i] == "--overwrite":
            overwrite = True; i += 1
        else:
            i += 1
    try:
        if cmd == "export":
            manifest = bk.export_backup(out_path, data_root or _TMP / "data_src", password)
            return 0, json.dumps({"ok": True, "files": manifest["file_count"]}, ensure_ascii=False)
        if cmd == "verify":
            r = bk.verify_backup(in_path, password)
            return 0, json.dumps(r, ensure_ascii=False, default=str)
        if cmd == "list":
            r = bk.list_backup(in_path, password)
            return 0, json.dumps({"files": r["files"]}, ensure_ascii=False)
        if cmd == "import":
            r = bk.import_backup(in_path, data_root, password, overwrite)
            return 0, json.dumps({"written": r["written"], "snapshot": r["snapshot"]}, ensure_ascii=False)
    except Exception as exc:
        return 1, str(exc)
    return 1, "unknown cmd"


class BackupExportImportTests(unittest.TestCase):

    def setUp(self):
        # 重置 data_dst
        dst = _TMP / "data_dst"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(REPO_ROOT / "data", dst)

    def test_export_no_password(self):
        out = _TMP / "no_pwd.songworkbench"
        rc, msg = _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        self.assertEqual(rc, 0, f"export 失败: {msg}")
        self.assertTrue(out.exists(), "未生成 .songworkbench 文件")
        self.assertGreater(out.stat().st_size, 1024, "备份文件过小")

    def test_export_with_password(self):
        out = _TMP / "with_pwd.songworkbench"
        rc, msg = _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"), "--password", "secret123")
        self.assertEqual(rc, 0, f"export 失败: {msg}")
        self.assertTrue(out.exists())

    def test_verify_correct_password(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"), "--password", "secret")
        rc, msg = _run_backup_inprocess("verify", "--input", str(out), "--password", "secret")
        result = json.loads(msg)
        self.assertEqual(rc, 0)
        self.assertTrue(result["ok"], f"verify 应 ok，结果: {result}")
        self.assertEqual(result["hmac_ok"], True)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["mismatched"], [])

    def test_verify_wrong_password_rejected(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"), "--password", "secret")
        rc, msg = _run_backup_inprocess("verify", "--input", str(out), "--password", "WRONG")
        self.assertEqual(rc, 1, "错密码应该拒绝")
        # M2.1：错密码先在 AES 层被 pyzipper 拒绝（不解密就没法读到 manifest/HMAC）
        # 所以错误信息是「密码错误或备份已损坏」而不是「HMAC 校验失败」
        self.assertIn("密码错误", msg)

    def test_verify_no_password_when_required_rejected(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"), "--password", "secret")
        rc, msg = _run_backup_inprocess("verify", "--input", str(out))
        self.assertEqual(rc, 1, "无密码应拒绝（备份需要密码）")

    def test_verify_no_password_for_unsigned_backup(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        rc, msg = _run_backup_inprocess("verify", "--input", str(out))
        result = json.loads(msg)
        self.assertEqual(rc, 0)
        self.assertTrue(result["ok"])

    def test_tampered_file_detected(self):
        """篡改 zip 内的某个文件 → verify 应检测 SHA-256 不一致。"""
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        # 篡改：往 zip 里塞一个坏文件，覆写 songs.json
        import zipfile
        with zipfile.ZipFile(out, "r") as zf:
            members = {m: zf.read(m) for m in zf.namelist()}
        members["songs.json"] = b'{"tampered": true}'
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        rc, msg = _run_backup_inprocess("verify", "--input", str(out))
        result = json.loads(msg)
        self.assertFalse(result["ok"], f"篡改应被检测，结果: {result}")
        self.assertGreater(len(result["mismatched"]), 0)

    def test_list_returns_manifest_and_files(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        rc, msg = _run_backup_inprocess("list", "--input", str(out))
        result = json.loads(msg)
        self.assertEqual(rc, 0)
        self.assertIn("songs.json", result["files"])
        self.assertIn("settings.json", result["files"])
        self.assertNotIn("manifest.json", result["files"])
        self.assertNotIn("manifest.hmac", result["files"])

    def test_import_creates_snapshot(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        rc, msg = _run_backup_inprocess("import", "--input", str(out), "--data-root", str(_TMP / "data_dst"), "--overwrite")
        result = json.loads(msg)
        self.assertEqual(rc, 0, f"import 失败: {msg}")
        self.assertIsNotNone(result["snapshot"])
        snapshot_path = _TMP / "data_dst" / result["snapshot"]
        self.assertTrue(snapshot_path.exists(), f"快照文件不存在: {snapshot_path}")

    def test_import_without_overwrite_rejects_existing_files(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        rc, msg = _run_backup_inprocess("import", "--input", str(out), "--data-root", str(_TMP / "data_dst"))
        self.assertEqual(rc, 1, "未带 --overwrite 应拒绝已存在文件")

    def test_import_with_wrong_password_rejected(self):
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"), "--password", "secret")
        rc, msg = _run_backup_inprocess("import", "--input", str(out), "--data-root", str(_TMP / "data_dst"), "--password", "wrong")
        self.assertEqual(rc, 1)

    def test_backup_schema_version(self):
        """备份 manifest 必须声明 schema_version=2（M2.1 升级）。"""
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        from tools import backup as bk
        zf, manifest, _, _ = bk._read_zip(out, None)
        zf.close()
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["app"], "streamer-workbench")
        self.assertGreater(manifest["file_count"], 0)

    def test_corrupted_zip_rejected(self):
        """完全损坏的 zip 应被拒绝（不是合法 backup）。"""
        out = _TMP / "corrupt.songworkbench"
        out.write_bytes(b"not a valid zip file at all")
        rc, msg = _run_backup_inprocess("verify", "--input", str(out))
        self.assertEqual(rc, 1)
        self.assertIn("损坏", msg)


class M21AesEncryptionTests(unittest.TestCase):
    """M2.1 AES-256 真加密 — 替换 M0.4 stdlib ZipCrypto 的 MVP 警告。

    关键差异（M2.1 vs M0.4）：
    - M0.4: zipfile.setpassword 套 stdlib ZipCrypto，错密码也会"读出原文"
    - M2.1: pyzipper.AESZipFile WZ_AES nbits=256，错密码 raise RuntimeError
    """

    def setUp(self):
        from tools import backup as bk
        self.bk = bk
        # 准备测试 data
        self.tmp = _TMP / "aes"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.src = self.tmp / "data_src"
        if self.src.exists():
            shutil.rmtree(self.src)
        self.src.mkdir()
        (self.src / "songs.json").write_text('{"songs": [{"id": "s1", "title": "测试"}], "version": 5}')
        (self.src / "settings.json").write_text('{"default_canvas": "9:20"}')
        self.out = self.tmp / "aes.songworkbench"

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp)

    def test_aes_export_with_password_succeeds(self):
        """密码模式导出成功（AES-256 真加密）。"""
        manifest = self.bk.export_backup(self.out, self.src, password="mySecret123")
        self.assertTrue(self.out.exists())
        self.assertGreater(self.out.stat().st_size, 0)
        self.assertEqual(manifest["schema_version"], 2)

    def test_aes_export_correct_password_round_trip(self):
        """正确密码：export → import 完整还原。"""
        self.bk.export_backup(self.out, self.src, password="mySecret123")
        # import 到新目录
        dst = self.tmp / "restored"
        if dst.exists():
            shutil.rmtree(dst)
        result = self.bk.import_backup(self.out, dst, password="mySecret123", overwrite=True)
        self.assertTrue((dst / "songs.json").exists())
        self.assertTrue((dst / "settings.json").exists())
        songs = json.loads((dst / "songs.json").read_text())
        self.assertEqual(songs["songs"][0]["title"], "测试")
        self.assertGreater(len(result["written"]), 0)

    def test_aes_export_wrong_password_rejected_at_decrypt(self):
        """M2.1 关键测试：错密码真拒绝（不解密就拿不到 manifest）。

        M0.4 旧实现：stdlib ZipCrypto 错密码也返回"原文"（CRC 校验不严）
        M2.1 新实现：pyzipper AES 错密码 raise RuntimeError → ValueError
        """
        self.bk.export_backup(self.out, self.src, password="correctPassword")
        with self.assertRaises(ValueError) as ctx:
            self.bk.import_backup(self.out, self.tmp / "no", password="WRONG_PASSWORD", overwrite=True)
        # 错误信息应明示密码错
        self.assertIn("密码错误", str(ctx.exception))

    def test_aes_export_no_password_provided_when_required_rejected(self):
        """加密备份要求密码时，不传密码应被拒绝。"""
        self.bk.export_backup(self.out, self.src, password="mySecret123")
        with self.assertRaises(ValueError) as ctx:
            self.bk.import_backup(self.out, self.tmp / "no", password=None, overwrite=True)
        # pyzipper 不传密码去读 AES 加密 zip 也会报错
        self.assertIn("密码", str(ctx.exception))

    def test_aes_file_not_readable_by_stdlib_zipfile(self):
        """M2.1 关键安全测试：AES 加密 zip 不能被 stdlib zipfile 解出原文。

        验证 stdlib 真的拿不到内容（即使知道文件名）。
        这正是 M0.4 失败的地方。
        """
        self.bk.export_backup(self.out, self.src, password="mySecret123")
        with zipfile.ZipFile(self.out, "r") as zf:
            # stdlib zipfile 仍能列出文件名（zip 头未加密）
            names = zf.namelist()
            self.assertIn("manifest.json", names)
            # 试读 manifest → stdlib 拒绝（encrypted 标志位 + 没密码）
            with self.assertRaises(RuntimeError) as ctx:
                zf.read("manifest.json")
            self.assertIn("encrypted", str(ctx.exception).lower(),
                          f"stdlib 报错应该提到 encrypted，实际: {ctx.exception}")

    @staticmethod
    def _looks_like_valid_manifest(raw: bytes) -> bool:
        """manifest 应是 JSON 含 schema_version 字段。"""
        try:
            obj = json.loads(raw)
            return isinstance(obj, dict) and "schema_version" in obj
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

    def test_aes_no_password_export_still_works(self):
        """无密码导出仍走 stdlib zipfile（向后兼容 M0.4）。"""
        self.bk.export_backup(self.out, self.src, password=None)
        # stdlib 能读（无加密）
        with zipfile.ZipFile(self.out, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["schema_version"], 2)

    def test_old_v1_backup_still_readable(self):
        """向后兼容：M0.4 的 v1 备份（无密码 + stdlib zip）仍可读取。

        构造一个 schema_version=1 的 v1 备份，用 _read_zip 读应该成功。
        """
        # 手工构造一个 v1 备份
        v1_out = self.tmp / "v1.songworkbench"
        manifest = {
            "schema_version": 1,
            "app": "streamer-workbench",
            "created_at": "2026-07-01T00:00:00Z",
            "file_count": 1,
            "total_bytes": 100,
            "files": [],
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        # 简单签（用 None 密码兼容 v1）
        hmac_sig = self.bk._sign_manifest(manifest_bytes, None)
        with zipfile.ZipFile(v1_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(self.bk.MANIFEST_NAME, manifest_bytes)
            zf.writestr(self.bk.HMAC_FILE, hmac_sig)
            zf.writestr("songs.json", b'{"songs": []}')
            # 改 manifest 的 files 含 songs.json
        manifest["files"] = [{"path": "songs.json", "size": 10, "sha256": hashlib.sha256(b'{"songs": []}').hexdigest()}]
        manifest_bytes2 = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        hmac_sig2 = self.bk._sign_manifest(manifest_bytes2, None)
        with zipfile.ZipFile(v1_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(self.bk.MANIFEST_NAME, manifest_bytes2)
            zf.writestr(self.bk.HMAC_FILE, hmac_sig2)
            zf.writestr("songs.json", b'{"songs": []}')
        # 现在 v1 备份能被 _read_zip 读
        zf, m, names, hmac_ok = self.bk._read_zip(v1_out, None)
        zf.close()
        self.assertEqual(m["schema_version"], 1)
        self.assertTrue(hmac_ok)


if __name__ == "__main__":
    unittest.main()
