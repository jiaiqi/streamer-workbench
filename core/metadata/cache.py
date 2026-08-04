"""M2.7 本地元数据缓存。

设计原则：
- envelope 格式：{ fetched_at, payload }，TTL 检查是 cache 自己的事
- 原子写：tmp + os.replace，防止写到一半被 kill 导致缓存损坏
- key sanitize：只保留 [a-zA-Z0-9_-]，防止路径穿越
- 读失败静默返回 None：让上层重新拉
- TTL 默认 30 天，force=True 绕过
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30 天


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class MetadataCache:
    """本地元数据缓存。

    存储路径: <base_dir>/<provider>/<key>.json
    存储内容：任意 JSON 可序列化对象（dict / list / str / None）。
    业务层（router / provider）自己负责 payload 的结构，cache 层不解析。
    """

    def __init__(self, base_dir: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须为正数")
        self._base = Path(base_dir)
        self._ttl = ttl_seconds
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def get(self, provider: str, key: str, *, force: bool = False) -> Any:
        """读缓存。返回 None 表示未命中或过期。

        Args:
            provider: provider 名称（决定子目录）
            key: 缓存 key（一般是 song_id / "search:<type>:<keyword>"）
            force: True 时忽略 TTL

        Returns:
            任意 JSON 可序列化的 payload（dict/list/str/None），或 None 表示未命中
        """
        if not provider or not key:
            return None
        path = self._path(provider, key)
        if not path.is_file():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                envelope = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(envelope, dict):
            return None
        if not force and self._is_expired(envelope.get("fetched_at", "")):
            return None
        return envelope.get("payload")

    def put(self, provider: str, key: str, payload: Any) -> None:
        """写缓存。原子写（tmp + os.replace）。

        payload 必须是 JSON 可序列化的（dict / list / str / int / float / bool / None）。
        """
        if not provider or not key:
            raise ValueError("provider 和 key 必填")
        path = self._path(provider, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "fetched_at": _now_iso(),
            "payload": payload,
        }
        # 原子写：先写同目录 tmp（保证 os.replace 是同 fs）
        fd, tmp_path = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(envelope, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            # 失败清理 tmp
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def clear(self, provider: str | None = None) -> int:
        """清缓存。

        Args:
            provider: 只清该 provider 的缓存；None 清全部

        Returns:
            删除条目数
        """
        if not self._base.is_dir():
            return 0
        count = 0
        if provider:
            sub = self._base / provider
            if sub.is_dir():
                for f in sub.glob("*.json"):
                    f.unlink()
                    count += 1
                # 尝试删空目录（失败忽略）
                try:
                    sub.rmdir()
                except OSError:
                    pass
        else:
            for f in self._base.rglob("*.json"):
                f.unlink()
                count += 1
        return count

    def list_keys(self, provider: str) -> list[str]:
        """列出某 provider 下的所有 key（调试/管理用）。"""
        sub = self._base / provider
        if not sub.is_dir():
            return []
        return [p.stem for p in sub.glob("*.json")]

    # ── 内部辅助 ──

    def _is_expired(self, fetched_at: str) -> bool:
        dt = _parse_iso(fetched_at)
        if dt is None:
            return True
        return (datetime.now().astimezone() - dt).total_seconds() > self._ttl

    def _path(self, provider: str, key: str) -> Path:
        # key sanitize：只保留 [a-zA-Z0-9_-]
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        if not safe:
            raise ValueError(f"key '{key}' sanitize 后为空")
        return self._base / provider / f"{safe}.json"
