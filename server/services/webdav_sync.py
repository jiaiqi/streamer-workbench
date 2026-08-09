"""M2.2 WebDAV 同步应用服务。

职责：
- 凭证（URL/账号/密码）加密存 settings.json.webdav_config_encrypted
  （复用 M2.1 pyzipper.AES WinZip AES-256；同主密码在 SettingsView 输入）
- 复用 tools/backup.py 的 export_backup/import_backup（.songworkbench 包）
  做本地 ↔ 远程的对等同步
- 暴露应用层方法给 router：get_config / save_config / test / list / push / pull

设计原则：
- 凭证永不入 settings.json 明文；服务端加密字段名 webdav_config_encrypted
- 同步过程中临时解密，结束立即丢弃
- 同步前后自动创建本地快照（data/backups/snapshot-*.json）
- 错误：WebDavSyncError 基类 + 4 子类（auth/network/remote_not_found/remote_conflict）
"""
from __future__ import annotations

import base64
import io
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyzipper

from core.webdav import (
    WebDavClient,
    WebDavError,
    WebDavAuthError,
    WebDavNetworkError,
    WebDavNotFoundError,
    WebDavProtocolError,
    WebDavResource,
)
from tools.backup import (
    export_backup,
    import_backup,
    list_backup as backup_list,
    verify_backup as backup_verify,
)


# ── 错误类型 ───────────────────────────────────────────────────────

class WebDavSyncError(Exception):
    """WebDAV 同步应用服务错误基类。"""


class WebDavConfigInvalid(WebDavSyncError):
    """WebDAV 配置无效（缺字段 / 密码错误 / URL 不合法）。"""


class WebDavAuthFailed(WebDavSyncError):
    """服务端鉴权失败（密码错 / 账号被禁）。"""


class WebDavRemoteUnavailable(WebDavSyncError):
    """远端不可达（DNS / SSL / 超时 / 服务端 5xx）。"""


class WebDavRemoteNotFound(WebDavSyncError):
    """远端文件/目录不存在。"""


class WebDavLocalError(WebDavSyncError):
    """本地 IO / 备份包校验失败。"""


# ── 常量 ───────────────────────────────────────────────────────────

# 加密格式：pyzipper 用的临时 zip 容器只装一个 entry，密码是 settings_password。
# 字段名固定，settings.json 中不出现明文凭证。
CONFIG_FIELD = "webdav_config_encrypted"
CONFIG_VERSION = 1


# ── 凭证加解密 ─────────────────────────────────────────────────────

def _aes_zip_write(plaintext: bytes, password: str) -> bytes:
    """用 pyzipper.AES-256 把 plaintext 加密成 zip bytes（单 entry）。"""
    buf = io.BytesIO()
    with pyzipper.AESZipFile(
        buf, "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.setencryption(pyzipper.WZ_AES, nbits=256)
        zf.writestr("config.json", plaintext)
    return buf.getvalue()


def _aes_zip_read(cipher_bytes: bytes, password: str) -> bytes:
    """解 pyzipper 加密的 config 字节；错密码抛 WebDavConfigInvalid。"""
    try:
        with pyzipper.AESZipFile(io.BytesIO(cipher_bytes), "r") as zf:
            zf.setpassword(password.encode("utf-8"))
            return zf.read("config.json")
    except RuntimeError as exc:
        # pyzipper 错密码："Bad password for file ..."
        raise WebDavConfigInvalid(f"主密码错误或备份已损坏: {exc}") from exc
    except Exception as exc:
        raise WebDavConfigInvalid(f"配置解密失败: {exc}") from exc


# ── 服务主类 ───────────────────────────────────────────────────────

class WebDavSyncService:
    """WebDAV 同步服务（应用层门面）。"""

    def __init__(self, *, settings_service, data_root: Path):
        self._settings = settings_service
        self._data_root = data_root
        self._tmp_dir = data_root / "backups" / "webdav-tmp"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    # ── config 加解密（独立于 HTTP 业务） ──

    def _load_raw_config_field(self) -> dict[str, Any] | None:
        """从 settings 读加密的 webdav config；没有返回 None。"""
        settings = self._settings.get()
        enc = settings.get(CONFIG_FIELD)
        if not enc:
            return None
        if not isinstance(enc, dict):
            return None
        if enc.get("version") != CONFIG_VERSION:
            return None
        return enc

    @staticmethod
    def encrypt_config(plaintext_config: dict[str, Any],
                       password: str) -> dict[str, Any]:
        """把 {url, username, password, remote_dir} 加密成 settings 字段。

        主密码就是 settings 主密码（SettingsView 解锁用）。"""
        if not password:
            raise WebDavConfigInvalid("主密码不能为空")
        payload = dict(plaintext_config)
        payload["version"] = CONFIG_VERSION
        raw = _serialize_json(payload).encode("utf-8")
        cipher = _aes_zip_write(raw, password)
        return {
            "version": CONFIG_VERSION,
            "cipher_b64": base64.b64encode(cipher).decode("ascii"),
        }

    @staticmethod
    def decrypt_config(encrypted: dict[str, Any],
                       password: str) -> dict[str, Any]:
        """解 settings 字段为 {url, username, password, remote_dir}。"""
        if not isinstance(encrypted, dict) or "cipher_b64" not in encrypted:
            raise WebDavConfigInvalid("加密字段格式无效")
        try:
            cipher = base64.b64decode(encrypted["cipher_b64"])
        except Exception as exc:
            raise WebDavConfigInvalid(f"base64 解码失败: {exc}") from exc
        raw = _aes_zip_read(cipher, password)
        try:
            data = _deserialize_json(raw)
        except Exception as exc:
            raise WebDavConfigInvalid(f"配置 JSON 解析失败: {exc}") from exc
        for key in ("url", "username", "password", "remote_dir"):
            if key not in data:
                raise WebDavConfigInvalid(f"配置缺少字段: {key}")
        return data

    # ── 业务方法（被 router 调用） ──

    def get_config_public(self, *, password: str | None) -> dict[str, Any]:
        """脱敏读：永远不返回 password 明文；password=None 时不校验主密码。

        返回 {configured: bool, url, username, remote_dir, updated_at}。
        未配置返回 {configured: False}。
        """
        raw = self._load_raw_config_field()
        if not raw:
            return {"configured": False}
        if password is None:
            return {
                "configured": True,
                "url": "", "username": "", "remote_dir": "",
                "updated_at": "", "needs_unlock": True,
            }
        # 校验主密码
        try:
            cfg = self.decrypt_config(raw, password)
        except WebDavConfigInvalid:
            raise
        return {
            "configured": True,
            "url": cfg.get("url", ""),
            "username": cfg.get("username", ""),
            "remote_dir": cfg.get("remote_dir", ""),
            "updated_at": raw.get("updated_at", ""),
            "needs_unlock": False,
        }

    def save_config(self, *, url: str, username: str, password: str,
                    remote_dir: str, master_password: str) -> dict[str, Any]:
        """加密存配置到 settings。

        master_password：settings 主密码（用于加密）。
        password：WebDAV 服务密码（被加密存）。"""
        if not url or not url.startswith(("http://", "https://")):
            raise WebDavConfigInvalid("url 必须是 http:// 或 https://")
        if not remote_dir:
            raise WebDavConfigInvalid("remote_dir 不能为空")
        # remote_dir 必须以 / 开头（WebDAV 绝对路径形式）
        if not remote_dir.startswith("/"):
            remote_dir = "/" + remote_dir
        cfg = {
            "url": url.rstrip("/"),
            "username": username or "",
            "password": password or "",
            "remote_dir": remote_dir.rstrip("/") or "/",
        }
        encrypted = self.encrypt_config(cfg, master_password)
        encrypted["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # 走 settings_service.update 触发 CAS
        self._settings.update({CONFIG_FIELD: encrypted})
        return {"ok": True, "updated_at": encrypted["updated_at"]}

    def clear_config(self, *, master_password: str) -> dict[str, Any]:
        """清除配置（连同加密字段一起删）。"""
        # 触发一次解密校验，验证主密码对得上
        raw = self._load_raw_config_field()
        if raw is not None:
            self.decrypt_config(raw, master_password)  # 错则抛
        self._settings.update({CONFIG_FIELD: None})
        return {"ok": True, "updated_at": ""}

    def test_connection(self, *, url: str, username: str, password: str) -> dict[str, Any]:
        """用临时凭证测试连接（不写盘）。"""
        client = _make_client(url, username, password)
        return client.test_connection()

    def list_remote(self, *, master_password: str) -> list[dict[str, Any]]:
        """列出远端 backup 目录下的 .songworkbench 文件。"""
        cfg = self._unlock(master_password)
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        # 远端目录：remote_dir/backups/
        remote_dir = cfg["remote_dir"]
        backup_dir = _backup_subdir(remote_dir)
        try:
            client.ensure_collection(remote_dir)
            client.ensure_collection(backup_dir)
            resources = client.listdir(backup_dir, depth="1")
        except WebDavAuthError as exc:
            raise WebDavAuthFailed(str(exc)) from exc
        except WebDavNotFoundError as exc:
            raise WebDavRemoteNotFound(str(exc)) from exc
        except (WebDavNetworkError, WebDavProtocolError) as exc:
            raise WebDavRemoteUnavailable(str(exc)) from exc
        out = []
        for r in resources:
            if r.is_collection:
                continue
            name = r.href.rsplit("/", 1)[-1]
            if not name.endswith(".songworkbench"):
                continue
            out.append({
                "name": name,
                "href": r.href,
                "size": r.size,
                "last_modified": r.last_modified,
            })
        out.sort(key=lambda x: x["name"], reverse=True)
        return out

    def push(self, *, master_password: str) -> dict[str, Any]:
        """本地 → 远端：生成 .songworkbench 并 PUT 到 remote_dir/backups/。"""
        cfg = self._unlock(master_password)
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        remote_dir = cfg["remote_dir"]
        backup_dir = _backup_subdir(remote_dir)

        # 1) 本地生成 .songworkbench
        tmp_path = self._tmp_dir / _new_backup_name("push")
        try:
            manifest = export_backup(
                output=tmp_path,
                data_root=self._data_root,
                password=None,  # 上传时不再二次加密；远端走 HTTPS / 鉴权保护
            )
        except Exception as exc:
            raise WebDavLocalError(f"生成本地备份失败: {exc}") from exc

        # 2) 远端确保目录存在
        try:
            client.ensure_collection(remote_dir)
            client.ensure_collection(backup_dir)
        except WebDavAuthError as exc:
            raise WebDavAuthFailed(str(exc)) from exc
        except (WebDavNetworkError, WebDavProtocolError) as exc:
            raise WebDavRemoteUnavailable(str(exc)) from exc

        # 3) PUT
        remote_name = tmp_path.name
        remote_path = backup_dir + "/" + remote_name
        try:
            client.upload(remote_path, tmp_path.read_bytes())
        except WebDavAuthError as exc:
            raise WebDavAuthFailed(str(exc)) from exc
        except (WebDavNetworkError, WebDavProtocolError) as exc:
            raise WebDavRemoteUnavailable(str(exc)) from exc
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        return {
            "ok": True,
            "remote_path": remote_path,
            "remote_name": remote_name,
            "file_count": manifest.get("file_count", 0),
            "total_bytes": manifest.get("total_bytes", 0),
        }

    def pull(self, *, master_password: str, remote_name: str) -> dict[str, Any]:
        """远端 → 本地：GET 指定 .songworkbench 并 import 覆盖 data_root。"""
        cfg = self._unlock(master_password)
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        remote_dir = cfg["remote_dir"]
        backup_dir = _backup_subdir(remote_dir)
        # 防 path traversal：remote_name 只允许 [A-Za-z0-9_.-]
        if not _is_safe_backup_name(remote_name):
            raise WebDavConfigInvalid(f"远端文件名不合法: {remote_name}")
        remote_path = backup_dir + "/" + remote_name

        # 1) 拉到本地临时文件
        tmp_path = self._tmp_dir / ("pull-" + remote_name)
        try:
            try:
                payload = client.download(remote_path)
            except WebDavAuthError as exc:
                raise WebDavAuthFailed(str(exc)) from exc
            except WebDavNotFoundError as exc:
                raise WebDavRemoteNotFound(str(exc)) from exc
            except (WebDavNetworkError, WebDavProtocolError) as exc:
                raise WebDavRemoteUnavailable(str(exc)) from exc
            tmp_path.write_bytes(payload)

            # 2) verify + import
            verify = backup_verify(tmp_path, password=None)
            if not verify["ok"]:
                raise WebDavLocalError(
                    f"远端备份校验失败: missing={verify['missing']} "
                    f"mismatched={len(verify['mismatched'])} 项"
                )
            result = import_backup(
                input=tmp_path,
                data_root=self._data_root,
                password=None,
                overwrite=True,
            )
        except WebDavSyncError:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise WebDavLocalError(f"导入失败: {exc}") from exc

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {
            "ok": True,
            "remote_name": remote_name,
            "manifest": result.get("manifest", {}),
        }

    def test_remote_connection(self, *, master_password: str) -> dict[str, Any]:
        """用已存配置测试连接 + 列出 backup 目录。"""
        cfg = self._unlock(master_password)
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        result = client.test_connection()
        if not result["ok"]:
            return result
        # 顺便确保 backup 目录存在
        try:
            client.ensure_collection(cfg["remote_dir"])
            client.ensure_collection(_backup_subdir(cfg["remote_dir"]))
        except WebDavAuthError as exc:
            return {"ok": False, "status": 401, "message": str(exc)}
        except (WebDavNetworkError, WebDavProtocolError) as exc:
            return {"ok": False, "status": 0, "message": str(exc)}
        return {**result, "remote_dir": cfg["remote_dir"]}

    # ── M2.4 内部 push/pull（用已解密 cfg，避免上层再输主密码） ──

    def push_internal(self, cfg: dict[str, Any]) -> dict[str, Any]:
        """用已解密 cfg 直接 push。供 AutoSyncScheduler 调用。

        cfg = {url, username, password, remote_dir}。
        """
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        remote_dir = cfg["remote_dir"]
        backup_dir = _backup_subdir(remote_dir)
        tmp_path = self._tmp_dir / _new_backup_name("autopush")
        try:
            manifest = export_backup(
                output=tmp_path,
                data_root=self._data_root,
                password=None,
            )
            client.ensure_collection(remote_dir)
            client.ensure_collection(backup_dir)
            remote_name = tmp_path.name
            remote_path = backup_dir + "/" + remote_name
            client.upload(remote_path, tmp_path.read_bytes())
            return {
                "ok": True,
                "remote_path": remote_path,
                "remote_name": remote_name,
                "file_count": manifest.get("file_count", 0),
                "total_bytes": manifest.get("total_bytes", 0),
            }
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def list_remote_internal(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """用已解密 cfg 列出远端 backup 子目录。"""
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        backup_dir = _backup_subdir(cfg["remote_dir"])
        client.ensure_collection(cfg["remote_dir"])
        client.ensure_collection(backup_dir)
        return client.list(backup_dir)

    def pull_internal(self, cfg: dict[str, Any], remote_name: str) -> dict[str, Any]:
        """用已解密 cfg 直接 pull 远端指定 .songworkbench。"""
        if not _is_safe_backup_name(remote_name):
            raise WebDavConfigInvalid(f"远端文件名不合法: {remote_name}")
        client = _make_client(cfg["url"], cfg["username"], cfg["password"])
        remote_dir = cfg["remote_dir"]
        backup_dir = _backup_subdir(remote_dir)
        remote_path = backup_dir + "/" + remote_name
        tmp_path = self._tmp_dir / ("autopull-" + remote_name)
        try:
            payload = client.download(remote_path)
            tmp_path.write_bytes(payload)
            verify = backup_verify(tmp_path, password=None)
            if not verify["ok"]:
                raise WebDavLocalError(
                    f"远端备份校验失败: missing={verify['missing']} "
                    f"mismatched={len(verify['mismatched'])} 项"
                )
            result = import_backup(
                input=tmp_path,
                data_root=self._data_root,
                password=None,
            )
            return {
                "ok": True,
                "remote_name": remote_name,
                "added": result.get("added", 0),
                "skipped": result.get("skipped", 0),
            }
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def auto_run_once(self, *, master_password: str) -> dict[str, Any]:
        """执行一次自动同步：按 settings 中的 direction 跑 push/pull/both。

        返回 {ok, ran, push: {...}, pull: {...}, error}。
        """
        cfg = self._unlock(master_password)
        direction = (self._settings_service.get()
                     .get("webdav_auto_sync_direction") or "push")
        result: dict[str, Any] = {"ok": True, "ran": [direction]}
        try:
            if direction in ("push", "both"):
                result["push"] = self.push_internal(cfg)
            if direction in ("pull", "both"):
                # 自动 pull：取远端最新一份（按 list 第一个）拉下来
                items = self.list_remote_internal(cfg)
                if not items:
                    result["pull"] = {"ok": True, "skipped": "no_remote_files"}
                else:
                    latest = items[-1]  # list 一般按时间升序
                    name = latest.get("name") or latest.get("href", "").rstrip("/").split("/")[-1]
                    if not name or not _is_safe_backup_name(name):
                        result["pull"] = {"ok": False, "skipped": "invalid_remote_name"}
                    else:
                        result["pull"] = self.pull_internal(cfg, name)
        except (WebDavAuthError, WebDavAuthFailed) as exc:
            result["ok"] = False
            result["error"] = f"auth_failed: {exc}"
        except (WebDavNetworkError, WebDavRemoteUnavailable) as exc:
            result["ok"] = False
            result["error"] = f"remote_unavailable: {exc}"
        except (WebDavLocalError, Exception) as exc:  # noqa: BLE001
            result["ok"] = False
            result["error"] = f"local_error: {exc}"
        return result

    # ── 内部 helpers ──

    def _unlock(self, master_password: str) -> dict[str, Any]:
        """校验主密码 + 返回解密后的 config 字典。"""
        if not master_password:
            raise WebDavConfigInvalid("主密码不能为空")
        raw = self._load_raw_config_field()
        if not raw:
            raise WebDavConfigInvalid("尚未配置 WebDAV，请先保存配置")
        return self.decrypt_config(raw, master_password)


# ── 模块级 helpers ──────────────────────────────────────────────────

def _make_client(url: str, username: str, password: str) -> WebDavClient:
    return WebDavClient(url, username or "", password or "")


def _backup_subdir(remote_dir: str) -> str:
    """远端 backup 子目录路径：remote_dir 末尾若已是 /backups 不重复追加。

    - remote_dir = "/backups" → "/backups"
    - remote_dir = "/" → "/backups"
    - remote_dir = "/dav/streamer" → "/dav/streamer/backups"
    - remote_dir = "/dav/streamer/backups" → "/dav/streamer/backups"（不重复）
    """
    base = remote_dir.rstrip("/") or ""
    if base.endswith("/backups"):
        return base or "/backups"
    return (base + "/backups") if base else "/backups"


def _new_backup_name(prefix: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}.songworkbench"


def _is_safe_backup_name(name: str) -> bool:
    """只允许字母数字 + _ + . + -；防 path traversal。"""
    if not name or len(name) > 200:
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    return all(c.isalnum() or c in "._-" for c in name)


def _serialize_json(data: dict[str, Any]) -> str:
    import json
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _deserialize_json(raw: bytes) -> dict[str, Any]:
    import json
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("config JSON 必须是对象")
    return result
