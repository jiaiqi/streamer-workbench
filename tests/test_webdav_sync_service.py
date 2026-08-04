"""M2.2 WebDavSyncService 单测。

覆盖：
- 凭证加解密 round-trip
- 错主密码拒绝
- get_config_public 三态：未配置 / 已配置但未解锁 / 解锁后
- save_config 校验
- clear_config 走主密码校验
- push / pull / list_remote 通过 mock WebDavClient 验证
- path traversal 防御
- 错误类型映射
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from core.webdav import WebDavResource
from server.services.webdav_sync import (
    WebDavAuthFailed,
    WebDavConfigInvalid,
    WebDavLocalError,
    WebDavRemoteNotFound,
    WebDavRemoteUnavailable,
    WebDavSyncService,
    _aes_zip_read,
    _aes_zip_write,
    _is_safe_backup_name,
    CONFIG_FIELD,
    CONFIG_VERSION,
)


# ── 工具函数 ──────────────────────────────────────────────────────

def _make_service(data_root: Path) -> tuple[WebDavSyncService, MagicMock]:
    """构造 WebDavSyncService + 替换 settings_service 为 mock。"""
    settings = MagicMock()
    settings_data: dict = {}
    def _get():
        return dict(settings_data)
    def _update(changes):
        settings_data.update(changes)
        return dict(settings_data)
    settings.get.side_effect = _get
    settings.update.side_effect = _update
    svc = WebDavSyncService(settings_service=settings, data_root=data_root)
    svc._settings_data = settings_data  # 给测试直接访问
    return svc, settings


# ── 加密 / 解密 ──────────────────────────────────────────────────

class TestCredentialEncryption:
    def test_round_trip(self):
        cfg = {
            "url": "https://dav.example.com/streamer",
            "username": "alice",
            "password": "super-secret",
            "remote_dir": "/backups",
        }
        encrypted = WebDavSyncService.encrypt_config(cfg, password="master123")
        assert encrypted["version"] == CONFIG_VERSION
        assert "cipher_b64" in encrypted

        decrypted = WebDavSyncService.decrypt_config(encrypted, password="master123")
        assert decrypted["url"] == cfg["url"]
        assert decrypted["username"] == cfg["username"]
        assert decrypted["password"] == cfg["password"]
        assert decrypted["remote_dir"] == cfg["remote_dir"]

    def test_wrong_master_password(self):
        encrypted = WebDavSyncService.encrypt_config(
            {"url": "https://dav.example.com", "username": "u",
             "password": "p", "remote_dir": "/x"},
            password="master123",
        )
        with pytest.raises(WebDavConfigInvalid, match="主密码错误"):
            WebDavSyncService.decrypt_config(encrypted, password="wrong")

    def test_empty_master_password(self):
        with pytest.raises(WebDavConfigInvalid, match="主密码不能为空"):
            WebDavSyncService.encrypt_config({"url": "x"}, password="")

    def test_cipher_is_zip(self):
        encrypted = WebDavSyncService.encrypt_config(
            {"url": "https://x", "username": "u", "password": "p", "remote_dir": "/"},
            password="master",
        )
        import base64
        cipher = base64.b64decode(encrypted["cipher_b64"])
        # 应该是合法 zip 文件（PK\x03\x04 头）
        assert cipher[:4] == b"PK\x03\x04"

    def test_decrypt_corrupt_cipher(self):
        with pytest.raises(WebDavConfigInvalid):
            WebDavSyncService.decrypt_config(
                {"version": CONFIG_VERSION, "cipher_b64": "!!!"}, password="p")

    def test_decrypt_missing_cipher_field(self):
        with pytest.raises(WebDavConfigInvalid, match="格式无效"):
            WebDavSyncService.decrypt_config({}, password="p")

    def test_decrypt_invalid_json(self):
        # 构造一个有效 zip 但内部 config.json 是非法 JSON
        buf = __import__("io").BytesIO()
        import pyzipper
        with pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED,
                                  encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(b"master")
            zf.setencryption(pyzipper.WZ_AES, nbits=256)
            zf.writestr("config.json", b"{not valid json")
        import base64
        encrypted = {
            "version": CONFIG_VERSION,
            "cipher_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
        }
        with pytest.raises(WebDavConfigInvalid, match="JSON 解析失败"):
            WebDavSyncService.decrypt_config(encrypted, password="master")

    def test_decrypt_missing_required_field(self):
        # 加密时故意不写 password 字段
        encrypted = WebDavSyncService.encrypt_config(
            {"url": "https://x", "username": "u", "remote_dir": "/"},
            password="master",
        )
        # round-trip 后 password 字段会缺失 → 抛错
        with pytest.raises(WebDavConfigInvalid, match="缺少字段"):
            WebDavSyncService.decrypt_config(encrypted, password="master")


# ── get_config_public ─────────────────────────────────────────────

class TestGetConfigPublic:
    def test_unconfigured(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            result = svc.get_config_public(password=None)
            assert result == {"configured": False}

    def test_configured_but_unlocked(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com/streamer",
                username="alice",
                password="webdav-pwd",
                remote_dir="/backups",
                master_password="master123",
            )
            # 不提供 master_password → needs_unlock
            result = svc.get_config_public(password=None)
            assert result["configured"] is True
            assert result["needs_unlock"] is True
            assert result["url"] == ""  # 脱敏
            assert result["password"] == "" if "password" in result else True  # 永不出

    def test_unlocked_returns_full(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com/streamer",
                username="alice",
                password="webdav-pwd",
                remote_dir="/backups",
                master_password="master123",
            )
            result = svc.get_config_public(password="master123")
            assert result["configured"] is True
            assert result["needs_unlock"] is False
            assert result["url"] == "https://dav.example.com/streamer"
            assert result["username"] == "alice"
            assert result["remote_dir"] == "/backups"
            assert "updated_at" in result

    def test_wrong_master_password(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/",
                master_password="master123",
            )
            with pytest.raises(WebDavConfigInvalid):
                svc.get_config_public(password="wrong")


# ── save_config 校验 ─────────────────────────────────────────────

class TestSaveConfig:
    def test_url_validation(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            for bad in ("ftp://x", "no-scheme", "", "javascript:alert(1)"):
                with pytest.raises(WebDavConfigInvalid, match="http"):
                    svc.save_config(
                        url=bad, username="u", password="p", remote_dir="/",
                        master_password="m",
                    )

    def test_remote_dir_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            result = svc.save_config(
                url="https://dav.example.com/streamer",
                username="u", password="p",
                remote_dir="backups",  # 无前导 /
                master_password="master",
            )
            assert result["ok"] is True
            # 读回：remote_dir 应补上 /
            public = svc.get_config_public(password="master")
            assert public["remote_dir"] == "/backups"

    def test_remote_dir_required(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            with pytest.raises(WebDavConfigInvalid, match="remote_dir"):
                svc.save_config(
                    url="https://dav.example.com",
                    username="u", password="p", remote_dir="",
                    master_password="m",
                )

    def test_persists_to_settings(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _settings = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/x",
                master_password="master",
            )
            # 通过 settings 查 cipher_b64 字段
            data = svc._settings_data
            assert CONFIG_FIELD in data
            assert data[CONFIG_FIELD]["version"] == CONFIG_VERSION
            assert "cipher_b64" in data[CONFIG_FIELD]
            assert data[CONFIG_FIELD]["updated_at"]


# ── clear_config ─────────────────────────────────────────────────

class TestClearConfig:
    def test_unconfigured_clear(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            # 未配置也允许 clear（不做密码校验）
            result = svc.clear_config(master_password="anything")
            assert result["ok"] is True

    def test_clears_field(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/",
                master_password="master",
            )
            assert CONFIG_FIELD in svc._settings_data
            svc.clear_config(master_password="master")
            assert svc._settings_data[CONFIG_FIELD] is None

    def test_wrong_master_password(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/",
                master_password="master",
            )
            with pytest.raises(WebDavConfigInvalid):
                svc.clear_config(master_password="wrong")


# ── path traversal 防御 ──────────────────────────────────────────

class TestSafeBackupName:
    @pytest.mark.parametrize("name,expected", [
        ("push-20260804T120000Z.songworkbench", True),
        ("file.zip", True),
        ("file_name.songworkbench", True),
        ("", False),
        ("../etc/passwd", False),
        ("..", False),
        ("sub/file.zip", False),
        ("sub\\file.zip", False),
        ("file\x00.zip", False),
        ("a" * 201, False),  # too long
    ])
    def test_check(self, name, expected):
        assert _is_safe_backup_name(name) is expected


# ── push / pull / list_remote：mock WebDavClient ─────────────────

class TestPush:
    def test_push_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 构造 data_root 内的样例文件
            (root / "songs.json").write_text('{"songs": []}', encoding="utf-8")
            (root / "settings.json").write_text('{}', encoding="utf-8")
            svc, _ = _make_service(root)
            svc.save_config(
                url="https://dav.example.com/streamer",
                username="u", password="p", remote_dir="/backups",
                master_password="master",
            )
            # mock WebDavClient
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.ensure_collection.return_value = None
                client.upload.return_value = None
                mc.return_value = client
                result = svc.push(master_password="master")
            assert result["ok"] is True
            assert result["remote_path"].startswith("/backups/push-")
            assert result["remote_path"].endswith(".songworkbench")
            assert client.upload.call_count == 1
            # 推送的内容是合法 zip（含 manifest.json）
            uploaded_bytes = client.upload.call_args[0][1]
            assert uploaded_bytes[:4] == b"PK\x03\x04"

    def test_push_no_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 空 data_root
            svc, _ = _make_service(root)
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/backups",
                master_password="master",
            )
            with pytest.raises(WebDavLocalError, match="生成本地备份失败"):
                svc.push(master_password="master")

    def test_push_unauthorized(self):
        from core.webdav import WebDavAuthError
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "songs.json").write_text("{}", encoding="utf-8")
            (root / "settings.json").write_text("{}", encoding="utf-8")
            svc, _ = _make_service(root)
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/x",
                master_password="master",
            )
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.ensure_collection.side_effect = WebDavAuthError("401")
                mc.return_value = client
                with pytest.raises(WebDavAuthFailed):
                    svc.push(master_password="master")

    def test_push_network_error(self):
        from core.webdav import WebDavNetworkError
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "songs.json").write_text("{}", encoding="utf-8")
            (root / "settings.json").write_text("{}", encoding="utf-8")
            svc, _ = _make_service(root)
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/x",
                master_password="master",
            )
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.ensure_collection.side_effect = WebDavNetworkError("dns fail")
                mc.return_value = client
                with pytest.raises(WebDavRemoteUnavailable):
                    svc.push(master_password="master")


class TestListRemote:
    def test_list_filters_collections(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/backups",
                master_password="master",
            )
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.ensure_collection.return_value = None
                client.listdir.return_value = [
                    WebDavResource(
                        href="/backups/old/", is_collection=True, size=0,
                        last_modified="Mon, 04 Aug 2026",
                    ),
                    WebDavResource(
                        href="/backups/a.songworkbench", is_collection=False,
                        size=100, last_modified="",
                    ),
                    WebDavResource(
                        href="/backups/random.txt", is_collection=False,
                        size=50, last_modified="",
                    ),
                    WebDavResource(
                        href="/backups/b.songworkbench", is_collection=False,
                        size=200, last_modified="",
                    ),
                ]
                mc.return_value = client
                files = svc.list_remote(master_password="master")
                # 只保留 .songworkbench 文件
                names = [f["name"] for f in files]
                assert "a.songworkbench" in names
                assert "b.songworkbench" in names
                assert "old" not in names
                assert "random.txt" not in names
                # 倒序
                assert names == sorted(names, reverse=True)


class TestPull:
    def test_pull_success(self):
        """构造一个本地 .songworkbench，mock 远端 download 返回它，再 import。"""
        import zipfile
        from tools.backup import export_backup

        with tempfile.TemporaryDirectory() as td:
            src_root = Path(td) / "src"
            dst_root = Path(td) / "dst"
            src_root.mkdir()
            dst_root.mkdir()
            (src_root / "songs.json").write_text(
                '{"version": 4, "songs": [{"id": "x", "title": "remote song"}]}',
                encoding="utf-8",
            )
            (src_root / "settings.json").write_text("{}", encoding="utf-8")
            # 生成 .songworkbench 到内存
            import io
            import hashlib
            buf = io.BytesIO()
            files = [src_root / "songs.json", src_root / "settings.json"]
            file_entries = [
                {
                    "path": str(p.relative_to(src_root)),
                    "size": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
                for p in files
            ]
            manifest = {
                "schema_version": 2, "app": "streamer-workbench",
                "created_at": "2026-08-04T00:00:00Z",
                "data_root": "src",
                "file_count": len(file_entries),
                "total_bytes": sum(e["size"] for e in file_entries),
                "files": file_entries,
            }
            manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", manifest_bytes)
                # 无密码模式必须 :unsigned 结尾才能过 verify
                zf.writestr("manifest.hmac", "x" * 64 + ":unsigned")
                for p in files:
                    zf.write(p, arcname=str(p.relative_to(src_root)))
            payload = buf.getvalue()

            svc, _ = _make_service(dst_root)
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/backups",
                master_password="master",
            )
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.download.return_value = payload
                mc.return_value = client
                result = svc.pull(
                    master_password="master",
                    remote_name="from-cloud.songworkbench",
                )
            assert result["ok"] is True
            # 数据被导入
            assert (dst_root / "songs.json").exists()
            assert "remote song" in (dst_root / "songs.json").read_text(encoding="utf-8")

    def test_pull_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/x",
                master_password="master",
            )
            with pytest.raises(WebDavConfigInvalid, match="不合法"):
                svc.pull(master_password="master", remote_name="../etc/passwd")

    def test_pull_remote_not_found(self):
        from core.webdav import WebDavNotFoundError
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/x",
                master_password="master",
            )
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.download.side_effect = WebDavNotFoundError("404")
                mc.return_value = client
                with pytest.raises(WebDavRemoteNotFound):
                    svc.pull(master_password="master", remote_name="x.songworkbench")

    def test_pull_corrupt_backup(self):
        """远端下载了一个不合法 zip，verify 应失败。"""
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            svc.save_config(
                url="https://dav.example.com",
                username="u", password="p", remote_dir="/x",
                master_password="master",
            )
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.download.return_value = b"NOT A ZIP"
                mc.return_value = client
                with pytest.raises(WebDavLocalError):
                    svc.pull(master_password="master", remote_name="bad.songworkbench")


# ── 内部 _unlock ─────────────────────────────────────────────────

class TestUnlock:
    def test_no_config(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            with pytest.raises(WebDavConfigInvalid, match="尚未配置"):
                svc._unlock("master")

    def test_empty_password(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            with pytest.raises(WebDavConfigInvalid, match="主密码不能为空"):
                svc._unlock("")


# ── test_connection（临时凭证） ───────────────────────────────────

class TestTestConnection:
    def test_success(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _make_service(Path(td))
            with patch("server.services.webdav_sync._make_client") as mc:
                client = MagicMock()
                client.test_connection.return_value = {"ok": True, "status": 207,
                                                      "message": "ok"}
                mc.return_value = client
                result = svc.test_connection(
                    url="https://dav.example.com",
                    username="u", password="p",
                )
                assert result["ok"] is True
