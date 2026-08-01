"""R8.0 弹唱：音频附件存储层（data/audio/{song_id}/）。

复用 `data/tabs/{song_id}/` 模式：扩展名白名单 + 大小上限 + 路径穿越防护。
v8.0 只做路径管理（保存/删除/校验），不做音频解码。
v8.1+ 在此基础上加：
  - 上传 API（POST /api/songs/{id}/audio）→ save_audio
  - 客户端音频解码 → audio_duration_ms 回填
  - Electron MediaSession metadata（title / artist / artwork）

设计
----
- 物理目录以不可变 song_id 为键（与 tabs 一致；改名不迁移）
- Song.audio_vocal_path / audio_instrumental_path 保存相对 data/ 的路径
  （如 "audio/song_…/vocal.mp3"）
- 单一 audio / 多个 audio：v8.0 只支持 2 个（vocal / instrumental），
  命名固定为 vocal.{ext} / instrumental.{ext}；重名自动加 -1/-2 后缀

约束
----
- ALLOWED_EXT：常见浏览器/Electron 都支持的格式
- MAX_FILE_BYTES：50MB（10 分钟 320kbps MP3 ≈ 24MB；留余量）
- 路径校验：relpath 必须落在 audio/{song_id}/ 下，且不能含 .. 段
"""
from __future__ import annotations

import os
import re
import unicodedata


# 扩展名白名单
ALLOWED_EXT = {".mp3", ".m4a", ".ogg", ".wav", ".webm"}
# 上限 50MB
MAX_FILE_BYTES = 50 * 1024 * 1024

# 与 tabs.py 对齐：Song.id 严格校验防目录穿越
SONG_ID_RE = re.compile(r"^song_[0-9a-f]{32}$")

# 角色命名（vocal / instrumental）
AUDIO_ROLES = ("vocal", "instrumental")


def sanitize_name(name: str) -> str:
    """文件名安全清洗：去路径分隔符与开头点，防目录穿越。"""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("/", "_").replace("\\", "_").strip().lstrip(".")
    return name[:80] or "未命名"


def _song_dir(audio_root: str, song_id: str) -> str:
    """拿到 audio/{song_id}/ 绝对路径。

    audio_root 是 data 根（与 SongLibrary 视角一致：audio_root/audio/{song_id}/）。
    非法 song_id 抛 ValueError。
    """
    if not SONG_ID_RE.match(song_id or ""):
        raise ValueError(f"非法 song_id：{song_id!r}（音频目录只接受稳定 song_id）")
    return os.path.join(audio_root, "audio", song_id)


def _safe_relpath(audio_root: str, song_id: str, relpath: str) -> str | None:
    """校验 relpath 落在 audio/{song_id}/ 下，且不含 .. 段。返回绝对路径或 None。

    audio_root 是 data 根；relpath 形如 "audio/{song_id}/file.mp3"。
    拼回 audio_root/relpath = data_root/audio/{song_id}/file.mp3。
    """
    if not SONG_ID_RE.match(song_id or ""):
        return None
    prefix = f"audio/{song_id}/"
    if not relpath.startswith(prefix) or ".." in relpath.split("/"):
        return None
    return os.path.join(audio_root, relpath)


def save_audio(audio_root: str, song_id: str, role: str, filename: str,
               data: bytes) -> str:
    """保存音频文件，返回相对 data/ 的路径。

    - role: "vocal" / "instrumental"（不在 AUDIO_ROLES 抛 ValueError）
    - filename: 原始文件名（仅用于扩展名检测；实际存盘名 = role + ext）
    - 扩展名白名单 + 大小上限校验
    """
    if role not in AUDIO_ROLES:
        raise ValueError(f"不支持的音频角色：{role!r}（仅 {AUDIO_ROLES}）")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型：{ext or '（无扩展名）'}（允许 {sorted(ALLOWED_EXT)}）")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024}MB 上限")

    d = _song_dir(audio_root, song_id)
    os.makedirs(d, exist_ok=True)
    base = role
    candidate, i = f"{base}{ext}", 1
    while os.path.exists(os.path.join(d, candidate)):
        candidate = f"{base}-{i}{ext}"
        i += 1
    with open(os.path.join(d, candidate), "wb") as f:
        f.write(data)
    return f"audio/{song_id}/{candidate}"


def delete_audio(audio_root: str, song_id: str, relpath: str) -> bool:
    """删除音频文件。relpath 必须落在 audio/{song_id}/ 下。

    非法 song_id 抛 ValueError；relpath 越界/不合法返 False。
    返回是否真的删除了文件（不存在则返 False）。
    """
    if not SONG_ID_RE.match(song_id or ""):
        raise ValueError(f"非法 song_id：{song_id!r}")
    abs_path = _safe_relpath(audio_root, song_id, relpath)
    if abs_path is None:
        return False
    if os.path.isfile(abs_path):
        os.unlink(abs_path)
        return True
    return False


def audio_exists(audio_root: str, song_id: str, relpath: str) -> bool:
    """校验音频文件存在。relpath 必须合法。"""
    abs_path = _safe_relpath(audio_root, song_id, relpath)
    if abs_path is None:
        return False
    return os.path.isfile(abs_path)


def list_audio(audio_root: str, song_id: str) -> tuple[str, ...]:
    """列出该歌的所有音频文件（仅文件名，role 通过前缀识别）。

    非法 song_id 抛 ValueError。
    """
    if not SONG_ID_RE.match(song_id or ""):
        raise ValueError(f"非法 song_id：{song_id!r}")
    d = _song_dir(audio_root, song_id)
    if not os.path.isdir(d):
        return ()
    return tuple(
        sorted(f for f in os.listdir(d)
               if os.path.isfile(os.path.join(d, f))
               and os.path.splitext(f)[1].lower() in ALLOWED_EXT)
    )


def parse_role_from_filename(filename: str) -> str | None:
    """从存盘文件名识别 role。

    "vocal.mp3" → "vocal"
    "vocal-1.mp3" → "vocal"
    "instrumental-2.m4a" → "instrumental"
    "其他.mp3" → None
    """
    base = os.path.splitext(os.path.basename(filename or ""))[0]
    for role in AUDIO_ROLES:
        if base == role or base.startswith(f"{role}-"):
            return role
    return None


__all__ = [
    "ALLOWED_EXT", "MAX_FILE_BYTES", "AUDIO_ROLES",
    "save_audio", "delete_audio", "audio_exists", "list_audio",
    "parse_role_from_filename",
]
