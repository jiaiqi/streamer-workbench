"""M0.4 蓝图 v0.1：加密备份包 MVP 测试。

覆盖：export / verify / list / import / HMAC 校验 / 密码错误拒绝 / 快照自动创建。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
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
        self.assertEqual(rc, 1, "错密码应该拒绝（HMAC 失败）")
        self.assertIn("HMAC", msg)

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
        """备份 manifest 必须声明 schema_version=1。"""
        out = _TMP / "v.songworkbench"
        _run_backup_inprocess("export", "--output", str(out), "--data-root", str(_TMP / "data_src"))
        from tools import backup as bk
        zf, manifest, _, _ = bk._read_zip(out, None)
        zf.close()
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["app"], "streamer-workbench")
        self.assertGreater(manifest["file_count"], 0)

    def test_corrupted_zip_rejected(self):
        """完全损坏的 zip 应被拒绝（不是合法 backup）。"""
        out = _TMP / "corrupt.songworkbench"
        out.write_bytes(b"not a valid zip file at all")
        rc, msg = _run_backup_inprocess("verify", "--input", str(out))
        self.assertEqual(rc, 1)
        self.assertIn("损坏", msg)


if __name__ == "__main__":
    unittest.main()
