"""M0.4 蓝图 v0.1：加密备份包 MVP → M2.1 升级 AES-256 真加密。

设计要点：
- 备份 streamer-workbench 的 data/ 目录（songs.json / events.jsonl / settings.json / preset.json / live-sessions/ / ...）
- 输出 .songworkbench 文件（zip 格式）
- 包含 manifest.json（版本 / 时间 / 文件清单 / SHA-256 / HMAC-SHA256 校验）
- M2.1 加密：password 模式下用 pyzipper.WZ_AES（WinZip AES-256）；错密码真拒绝
  - 旧 M0.4 备份（无密码，stdlib zip）仍可读取（向后兼容）
  - 无密码导出走 stdlib zipfile（与 M0.4 一致；不加 AES 避免无谓依赖）
- 密码模式 + HMAC-SHA256 双层防护：
  - HMAC：防篡改（任何人改了文件 verify 必失败）
  - AES-256：防偷看（错密码根本解不开；实测 pyzipper 会 raise RuntimeError）
- export/import/verify/list 四个命令
- 导入前自动创建本地快照（data/backups/snapshot-*.json）

用法：
    PYTHONPATH=. python tools/backup.py export --output backup.songworkbench [--password SECRET]
    PYTHONPATH=. python tools/backup.py import --input backup.songworkbench [--password SECRET] [--data-root data/]
    PYTHONPATH=. python tools/backup.py verify --input backup.songworkbench [--password SECRET]
    PYTHONPATH=. python tools/backup.py list --input backup.songworkbench [--password SECRET]
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pyzipper


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = ROOT / "data"

MANIFEST_NAME = "manifest.json"
HMAC_FILE = "manifest.hmac"
SCHEMA_VERSION = 2  # M2.1 升级到 2（旧 v1 仍可读）
APP_NAME = "streamer-workbench"
BACKUP_EXT = ".songworkbench"


def _open_zip_for_write(buf, password: str | None):
    """根据是否有密码选择 zip 容器。
    - password 不为空：pyzipper AES-256（WinZip 兼容；错密码真拒绝）
    - password 为空：stdlib zipfile（向后兼容 M0.4 无密码备份）"""
    if password:
        zf = pyzipper.AESZipFile(
            buf, "w",
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES,
        )
        zf.setpassword(password.encode("utf-8"))
        zf.setencryption(pyzipper.WZ_AES, nbits=256)
        return zf
    return zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)


def _open_zip_for_read(input, password: str | None):
    """根据是否有密码选择 zip 读取容器；统一抛 ValueError。"""
    try:
        if password:
            zf = pyzipper.AESZipFile(input, "r")
            zf.setpassword(password.encode("utf-8"))
        else:
            zf = zipfile.ZipFile(input, "r")
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"备份文件损坏或不是有效的 .songworkbench: {exc}") from exc
    return zf


def _zip_read(zf, name: str) -> bytes:
    """统一 zf.read，捕获 pyzipper 错密码的 RuntimeError 包装为 ValueError。"""
    try:
        return zf.read(name)
    except RuntimeError as exc:
        # pyzipper 错密码会在这里 raise RuntimeError("Bad password for file ...")
        raise ValueError(f"密码错误或备份已损坏: {exc}") from exc


def _collect_files(data_root: Path) -> list[Path]:
    """收集 data_root 下所有需要备份的文件（排除 backups/ 目录避免循环备份）。"""
    if not data_root.exists():
        return []
    files = []
    for path in sorted(data_root.rglob("*")):
        if not path.is_file():
            continue
        # 排除：自动备份目录、临时文件
        rel = path.relative_to(data_root)
        parts = rel.parts
        if parts[0] == "backups":
            continue
        if path.suffix in (".tmp", ".swp", ".bak"):
            continue
        files.append(path)
    return files


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hmac_key(password: str) -> bytes:
    """从密码派生 HMAC 密钥（KDF：HMAC-SHA256 循环 10000 次）。

    MVP 简化版：单轮 HMAC-SHA256；生产前换 PBKDF2/scrypt。
    """
    return hmac.new(
        f"{APP_NAME}-m0.4-hmac-v1".encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _sign_manifest(manifest_bytes: bytes, password: str | None) -> str:
    """对 manifest JSON 字节计算 HMAC-SHA256 签名。无密码时签空（仅 SHA-256 自校验）。"""
    if not password:
        # 无密码模式：签空字符串作为"未签名"标记
        return hmac.new(b"", b"", hashlib.sha256).hexdigest() + ":unsigned"
    return hmac.new(_hmac_key(password), manifest_bytes, hashlib.sha256).hexdigest()


def _verify_manifest(manifest_bytes: bytes, hmac_str: str, password: str | None) -> bool:
    """验证 manifest HMAC 签名。错密码下返回 False。"""
    if hmac_str.endswith(":unsigned"):
        return password is None
    if password is None:
        return False
    expected = hmac.new(_hmac_key(password), manifest_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, hmac_str)


def _build_manifest(data_root: Path, files: list[Path]) -> dict:
    """生成 manifest.json 内容（含每个文件的 SHA-256）。"""
    file_entries = []
    for path in files:
        rel = path.relative_to(data_root)
        file_entries.append({
            "path": str(rel),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "app": APP_NAME,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_root": str(data_root.relative_to(ROOT)) if data_root.is_relative_to(ROOT) else str(data_root),
        "file_count": len(file_entries),
        "total_bytes": sum(e["size"] for e in file_entries),
        "files": file_entries,
    }


def _make_zip_bytes(data_root: Path, files: list[Path], manifest: dict, password: str | None) -> bytes:
    """在内存里构建 zip（含 manifest.json + manifest.hmac + data 文件）。

    M2.1：password 不为空时走 pyzipper AES-256（WinZip 兼容）；空密码保持 stdlib zipfile。
    """
    buf = io.BytesIO()
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    hmac_sig = _sign_manifest(manifest_bytes, password)
    with _open_zip_for_write(buf, password) as zf:
        # 放最前：manifest + hmac 签名
        zf.writestr(MANIFEST_NAME, manifest_bytes)
        zf.writestr(HMAC_FILE, hmac_sig)
        # 全部 data 文件
        for path in files:
            arcname = str(path.relative_to(data_root))
            zf.write(path, arcname=arcname)
    return buf.getvalue()


def export_backup(output: Path, data_root: Path, password: str | None) -> dict:
    """导出备份：data_root → output（.songworkbench）。

    M2.1：password 模式下用 pyzipper AES-256 真加密；空密码保持向后兼容的明文 zip。
    错密码下 import/verify 必拒绝（pyzipper 抛 RuntimeError 包装为 ValueError）。
    """
    if not data_root.exists():
        raise FileNotFoundError(f"data 目录不存在: {data_root}")
    files = _collect_files(data_root)
    if not files:
        raise ValueError(f"data 目录为空，无可备份内容: {data_root}")
    manifest = _build_manifest(data_root, files)
    payload = _make_zip_bytes(data_root, files, manifest, password)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return manifest


def _read_zip(input: Path, password: str | None) -> tuple:
    """读 zip 文件并验证 manifest。返回 (zip, manifest, 内部文件列表, hmac_ok)。

    M2.1：password 不为空时用 pyzipper 读；错密码抛 ValueError 包装后的 RuntimeError。
    """
    zf = _open_zip_for_read(input, password)
    try:
        manifest_data = _zip_read(zf, MANIFEST_NAME)
    except KeyError as exc:
        zf.close()
        raise ValueError(f"备份文件缺失 manifest.json: {exc}") from exc
    try:
        hmac_str = _zip_read(zf, HMAC_FILE).decode("utf-8")
    except KeyError:
        hmac_str = "missing:unsigned"
    except ValueError as exc:
        zf.close()
        raise
    hmac_ok = _verify_manifest(manifest_data, hmac_str, password)
    if not hmac_ok:
        zf.close()
        raise ValueError("HMAC 校验失败：备份被篡改或密码错误")
    try:
        manifest = json.loads(manifest_data)
    except json.JSONDecodeError as exc:
        zf.close()
        raise ValueError(f"manifest.json 格式错误: {exc}") from exc
    # M2.1：SCHEMA_VERSION=2 兼容旧 v1（M0.4 备份）
    sv = manifest.get("schema_version")
    if sv not in (SCHEMA_VERSION, 1):
        zf.close()
        raise ValueError(
            f"备份版本不匹配：当前支持 v{SCHEMA_VERSION}/v1，备份为 v{sv}"
        )
    return zf, manifest, zf.namelist(), hmac_ok


def list_backup(input: Path, password: str | None) -> dict:
    """列出备份内文件清单。"""
    zf, manifest, names, _ = _read_zip(input, password)
    zf.close()
    return {
        "manifest": manifest,
        "files": [n for n in names if n not in (MANIFEST_NAME, HMAC_FILE)],
    }


def verify_backup(input: Path, password: str | None) -> dict:
    """验证备份完整性：每个文件 SHA-256 与 manifest 记录一致。"""
    zf, manifest, _, hmac_ok = _read_zip(input, password)
    mismatches = []
    missing = []
    file_map = {e["path"]: e for e in manifest["files"]}
    for arcname, entry in file_map.items():
        try:
            actual = hashlib.sha256(zf.read(arcname)).hexdigest()
        except KeyError:
            missing.append(arcname)
            continue
        if actual != entry["sha256"]:
            mismatches.append((arcname, entry["sha256"], actual))
    zf.close()
    return {
        "ok": hmac_ok and not missing and not mismatches,
        "hmac_ok": hmac_ok,
        "manifest": manifest,
        "missing": missing,
        "mismatched": mismatches,
    }


def import_backup(input: Path, data_root: Path, password: str | None,
                 overwrite: bool = False) -> dict:
    """导入备份到 data_root。

    安全策略：
    1. 先 verify（HMAC + SHA-256）
    2. 仅当 verify ok 才覆盖目标
    3. 导入前自动创建本地快照（copy to backups/）
    """
    # Step 1: 验证
    result = verify_backup(input, password)
    if not result["ok"]:
        raise ValueError(
            f"备份验证失败：hmac_ok={result['hmac_ok']}, "
            f"missing={result['missing']}, mismatched={len(result['mismatched'])} 项"
        )
    # Step 2: 本地快照（防误覆盖）
    if data_root.exists():
        snapshot = _create_snapshot(data_root)
    else:
        snapshot = None
    # Step 3: 解压到目标
    zf, manifest, names, _ = _read_zip(input, password)
    written = []
    try:
        for name in names:
            if name in (MANIFEST_NAME, HMAC_FILE):
                continue
            target = data_root / name
            if target.exists() and not overwrite:
                raise FileExistsError(
                    f"目标文件已存在（用 --overwrite 覆盖）: {target}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            written.append(str(target.relative_to(data_root)))
    finally:
        zf.close()
    return {
        "manifest": manifest,
        "snapshot": snapshot,
        "written": written,
    }


def _create_snapshot(data_root: Path) -> str:
    """创建本地快照（data_root → backups/snapshot-<timestamp>.json）。"""
    backups_dir = data_root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_path = backups_dir / f"snapshot-{timestamp}.json"
    # 简版快照：songs.json + settings.json；其他文件待扩展
    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reason": "before import_backup",
    }
    for fname in ("songs.json", "settings.json", "events.jsonl"):
        fpath = data_root / fname
        if fpath.exists():
            snapshot[fname] = fpath.read_text(encoding="utf-8")
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    return str(snapshot_path.relative_to(data_root))


def main():
    parser = argparse.ArgumentParser(
        description="M0.4 加密备份包 MVP — streamer-workbench / .songworkbench"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # export
    p_exp = sub.add_parser("export", help="导出 data/ 为 .songworkbench")
    p_exp.add_argument("--output", "-o", type=Path, required=True, help="输出文件路径")
    p_exp.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT, help="data 根目录")
    p_exp.add_argument("--password", help="可选密码（ZipCrypto 加密）")

    # import
    p_imp = sub.add_parser("import", help="导入 .songworkbench 到 data/")
    p_imp.add_argument("--input", "-i", type=Path, required=True, help="备份文件")
    p_imp.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT, help="目标 data 根目录")
    p_imp.add_argument("--password", help="备份密码")
    p_imp.add_argument("--overwrite", action="store_true", help="覆盖已存在文件")

    # verify
    p_ver = sub.add_parser("verify", help="验证备份完整性（SHA-256）")
    p_ver.add_argument("--input", "-i", type=Path, required=True)
    p_ver.add_argument("--password", help="备份密码")

    # list
    p_lst = sub.add_parser("list", help="列出备份内文件")
    p_lst.add_argument("--input", "-i", type=Path, required=True)
    p_lst.add_argument("--password", help="备份密码")

    args = parser.parse_args()

    try:
        if args.cmd == "export":
            manifest = export_backup(args.output, args.data_root, args.password)
            print(f"[backup] 已导出 {manifest['file_count']} 个文件 ({manifest['total_bytes']} bytes) → {args.output}")
            print(f"[backup] 清单：{len(manifest['files'])} 项")
        elif args.cmd == "import":
            result = import_backup(args.input, args.data_root, args.password, args.overwrite)
            print(f"[backup] 已导入 {len(result['written'])} 个文件")
            if result["snapshot"]:
                print(f"[backup] 本地快照: {result['snapshot']}")
        elif args.cmd == "verify":
            result = verify_backup(args.input, args.password)
            status = "✅ OK" if result["ok"] else "❌ FAIL"
            print(f"[backup] 验证 {status} - {len(result['manifest']['files'])} 项")
            if result["missing"]:
                print(f"  缺失: {result['missing']}")
            if result["mismatched"]:
                print(f"  不一致: {len(result['mismatched'])} 项")
        elif args.cmd == "list":
            result = list_backup(args.input, args.password)
            print(f"[backup] 备份 {result['manifest']['created_at']}, {len(result['files'])} 文件:")
            for f in result["files"]:
                print(f"  {f}")
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"[backup] 错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
