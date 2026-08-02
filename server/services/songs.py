"""歌曲写用例：以不可变 ID 为主，并集中协调 Repository 与事件。"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.data.events import _normalize_timestamp
from core.data.songs import Song, SongLibrary, pinyin_initials


class SongServiceError(Exception):
    """可由 HTTP 适配层稳定映射的歌曲用例错误。"""


class SongValidationFailed(SongServiceError):
    pass


class SongNotFound(SongServiceError):
    pass


class SongConflict(SongServiceError):
    pass


@dataclass(frozen=True)
class SongMutation:
    song: Song
    active: int
    draft: int
    added: tuple = ()  # 仅 seed-sample 路径使用；普通 create 留空


@dataclass(frozen=True)
class SongDeletion:
    song_id: str
    title_snapshot: str
    active: int
    draft: int


class SongApplicationService:
    """歌曲写入的唯一业务编排者；Router 不再直接保存或追加事件。"""

    def __init__(self, *, song_repository, event_store):
        self._songs = song_repository
        self._events = event_store

    def create(self, payload: Mapping[str, Any]) -> SongMutation:
        fields = clean_song_fields(payload)
        title = fields.pop("title", "")
        if not title:
            raise SongValidationFailed("歌名不能为空")
        # section=None 自动按字数计算 (对应前端「自动(按字数)」选项)
        if fields.get("section") is None:
            fields["section"] = _auto_section_from_title(title)
        status = payload.get("status")
        song = Song(
            title=title,
            status=status if status in ("active", "draft") else "draft",
            added_at=datetime.now().strftime("%Y-%m-%d"),
            **fields,
        )
        if not song.pinyin:
            song.pinyin = pinyin_initials(title)
        snapshot = self._songs.load()
        if not snapshot.value.add(song):
            raise SongConflict(f"歌曲已存在：{title}")
        self._save_and_report(
            snapshot, "song_added", song,
            meta={"status": song.status})
        return self._mutation(song, snapshot.value)

    def update_by_id(
        self, song_id: str, payload: Mapping[str, Any]
    ) -> SongMutation:
        return self._update("id", song_id, payload)

    def update_by_title(
        self, title: str, payload: Mapping[str, Any]
    ) -> SongMutation:
        return self._update("title", title.strip(), payload)

    def set_status_by_id(self, song_id: str, status: str) -> SongMutation:
        return self._set_status("id", song_id, status)

    def set_status_by_title(self, title: str, status: str) -> SongMutation:
        return self._set_status("title", title.strip(), status)

    def delete_by_id(self, song_id: str) -> SongDeletion:
        return self._delete("id", song_id)

    def delete_by_title(self, title: str) -> SongDeletion:
        return self._delete("title", title.strip())

    # ---- R9.6 软删除配套 ----

    def restore_by_id(self, song_id: str) -> "SongResponse":
        return self._restore("id", song_id)

    def restore_by_title(self, title: str) -> "SongResponse":
        return self._restore("title", title.strip())

    def purge_by_id(self, song_id: str) -> SongDeletion:
        return self._purge("id", song_id)

    def purge_by_title(self, title: str) -> SongDeletion:
        return self._purge("title", title.strip())

    def seed_sample_songs(self) -> SongMutation:
        """仅当曲库为空时载入内置样例曲库；非空返回当前 mutation 不写盘。"""
        snapshot = self._songs.load()
        library = snapshot.value
        if library.songs:
            # 非空库 → 拒绝导入以避免重复
            return SongMutation(
                song=library.songs[0],
                active=library.count_active(),
                draft=library.count_draft(),
                added=(),
            )
        from core.data.sample_songs import seed_to_library
        added = seed_to_library(library)
        if not added:
            return SongMutation(
                song=library.songs[0] if library.songs else None,
                active=library.count_active(),
                draft=library.count_draft(),
                added=(),
            )
        # 一次提交：批量导入 → song_added 事件（带 source_kind="sample_seed" 标记）
        self._songs.save(library, expected_revision=snapshot.revision)
        for song in added:
            self._append_seed_event(song)
        return SongMutation(
            song=added[-1],
            active=library.count_active(),
            draft=library.count_draft(),
            added=tuple(added),
        )

    def _append_seed_event(self, song) -> None:
        import uuid
        from core.data.events import _normalize_timestamp
        event = {
            "schema_version": 2,
            "event_id": f"evt_{uuid.uuid4().hex}",
            "occurred_at": _normalize_timestamp(None),
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": "song_added",
            "source": "sample-seed",
            "song_id": song.id,
            "title_snapshot": song.title,
            "meta": {"status": song.status, "source_kind": "sample_seed"},
        }
        self._events.append(event)

    def _update(
        self, identity_kind: str, identity: str, payload: Mapping[str, Any]
    ) -> SongMutation:
        fields = clean_song_fields(payload)
        if not fields:
            raise SongValidationFailed("fields 为空")
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, identity_kind, identity)
        old_view = song_values(song)
        try:
            library.update_by_id(song.id, fields)
        except ValueError as error:
            if "改名失败" in str(error):
                raise SongConflict(str(error)) from error
            raise SongValidationFailed(str(error)) from error
        # section=None → 自动按字数计算 (对应前端「自动」选项)
        current = library.get_by_id(song.id)
        if current is not None and current.section is None:
            current.section = _auto_section_from_title(current.title)
        # 如果用户显式改了 title, 且 section 是「自动」标记 (fields 不含 section),
        # 不应该触发重复计算。只有 section 在 fields 里且为 None 时触发。
        # 由于 _update 不删除 field 中 section, 我们上面的逻辑是:
        # 在 update_by_id 之后、save 之前, 如果 song.section 仍为 None,
        # 则按标题自动归类。
        current_view = song_values(current)
        changes = [
            {"field": key, "old": old_view.get(key), "new": current_view.get(key)}
            for key in fields
            if old_view.get(key) != current_view.get(key)
        ]
        self._save_and_report(
            snapshot, "song_edited", current, meta={"changes": changes})
        return self._mutation(current, library)

    def _set_status(
        self, identity_kind: str, identity: str, status: str
    ) -> SongMutation:
        status = status.strip()
        if status not in ("active", "draft"):
            raise SongValidationFailed("status 必须是 active 或 draft")
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, identity_kind, identity)
        if status == "active":
            library.mark_active_by_id(song.id)
            song.learned_at = datetime.now().strftime("%Y-%m-%d")
        else:
            library.mark_draft_by_id(song.id)
        self._save_and_report(
            snapshot,
            "song_learned" if status == "active" else "song_unlearned",
            song,
        )
        return self._mutation(song, library)

    def _delete(self, identity_kind: str, identity: str) -> SongDeletion:
        """R9.6 软删除：设置 deleted_at（30 天后 cleanup_expired 真删）。
        若 song 已经被删，则更新 deleted_at（刷新计时）。
        """
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, identity_kind, identity)
        now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
        library.soft_delete_by_id(song.id, now_iso)
        # save 报告（用 song 的当前字段，含 deleted_at）
        self._save_and_report(snapshot, "song_deleted", song)
        return SongDeletion(
            song.id, song.title, library.count_active(), library.count_draft())

    def _restore(self, identity_kind: str, identity: str) -> "SongResponse":
        """R9.6 恢复软删除：清空 deleted_at。"""
        from server.api.song_models import SongResponse
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, identity_kind, identity)
        library.restore_by_id(song.id)
        self._save_and_report(snapshot, "song_restored", song)
        return SongResponse(**song_values(song))

    def _purge(self, identity_kind: str, identity: str) -> SongDeletion:
        """R9.6 真删：不可恢复。"""
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, identity_kind, identity)
        library.purge_by_id(song.id)
        self._save_and_report(snapshot, "song_purged", song)
        return SongDeletion(
            song.id, song.title, library.count_active(), library.count_draft())

    # ── R8.1 弹唱：音频附件助手方法 ──

    def resolve_id(self, identity: str) -> str:
        """把 identity（id 或 title）解析为 song_id；找不到抛 SongNotFound。"""
        snapshot = self._songs.load()
        library = snapshot.value
        # 优先按 id 解析
        song = library.get_by_id(identity)
        if song is not None:
            return song.id
        # 兜底按 title
        song = library.get(identity)
        if song is not None:
            return song.id
        raise SongNotFound(f"未找到歌曲：{identity}")

    def resolve_audio_upload(
        self, identity: str, role: str, filename: str, data: bytes
    ) -> Song:
        """R8.1: 保存音频到 data/audio/{song_id}/ + 回写 Song 字段。

        role="vocal" → Song.audio_vocal_path
        role="instrumental" → Song.audio_instrumental_path
        """
        from core import audio as audio_storage  # 局部 import 避免循环
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, "id_or_title", identity)
        audio_root = str(self._songs._path.parent)  # data 根
        relpath = audio_storage.save_audio(audio_root, song.id, role, filename, data)
        # 回写 Song 字段
        fields = {f"audio_{role}_path": relpath}
        library.update_by_id(song.id, fields)
        # 不触发 _save_and_report 事件（音频上传是文件操作，不算业务变更）
        self._songs.save(library, expected_revision=snapshot.revision)
        # 重新 load 获取更新后的 Song
        updated = library.get_by_id(song.id)
        return updated if updated is not None else song

    def list_audio(self, identity: str) -> list[dict[str, Any]]:
        """R8.1: 列出该歌的所有音频文件（带 role 识别）。"""
        from core import audio as audio_storage
        song_id = self.resolve_id(identity)
        audio_root = str(self._songs._path.parent)
        files = audio_storage.list_audio(audio_root, song_id)
        items: list[dict[str, Any]] = []
        for filename in files:
            role = audio_storage.parse_role_from_filename(filename) or "unknown"
            ext = os.path.splitext(filename)[1].lower()
            items.append({
                "role": role,
                "filename": filename,
                "path": f"audio/{song_id}/{filename}",
                "mime": _audio_mime(ext),
            })
        return items

    def delete_audio(self, identity: str, role: str) -> list[dict[str, Any]]:
        """R8.1: 删除指定 role 的音频 + 清空 Song 字段。"""
        from core import audio as audio_storage
        song_id = self.resolve_id(identity)
        audio_root = str(self._songs._path.parent)
        song_field = f"audio_{role}_path"
        # 找到当前 relpath 才能删除
        snapshot = self._songs.load()
        library = snapshot.value
        song = library.get_by_id(song_id)
        if song is None:
            raise SongNotFound(f"未找到歌曲：{song_id}")
        relpath = getattr(song, song_field, "")
        if relpath:
            audio_storage.delete_audio(audio_root, song_id, relpath)
            # 清空 Song 字段
            library.update_by_id(song_id, {song_field: ""})
            self._songs.save(library, expected_revision=snapshot.revision)
        return self.list_audio(song_id)

    def audio_info(self, identity: str, role: str) -> dict[str, Any] | None:
        """R8.1: 音频文件元信息（不返回 FileResponse，仅 JSON）。"""
        from core import audio as audio_storage
        song_id = self.resolve_id(identity)
        audio_root = str(self._songs._path.parent)
        files = audio_storage.list_audio(audio_root, song_id)
        # 按 role 匹配第一个
        for filename in files:
            r = audio_storage.parse_role_from_filename(filename)
            if r == role:
                ext = os.path.splitext(filename)[1].lower()
                abs_path = os.path.join(audio_root, "audio", song_id, filename)
                size = os.path.getsize(abs_path) if os.path.isfile(abs_path) else 0
                return {
                    "song_id": song_id,
                    "role": role,
                    "filename": filename,
                    "path": f"audio/{song_id}/{filename}",
                    "size": size,
                    "mime": _audio_mime(ext),
                }
        return None

    def audio_abs_path(self, identity: str, role: str) -> str | None:
        """R8.1: 返回音频文件绝对路径（流式 FileResponse 用）。"""
        from core import audio as audio_storage
        song_id = self.resolve_id(identity)
        audio_root = str(self._songs._path.parent)
        files = audio_storage.list_audio(audio_root, song_id)
        for filename in files:
            r = audio_storage.parse_role_from_filename(filename)
            if r == role:
                return os.path.join(audio_root, "audio", song_id, filename)
        return None

    @staticmethod
    def _find(library: SongLibrary, identity_kind: str, identity: str) -> Song:
        # R8.1: id_or_title 模式兼容老 title 路由 + 新 song_id 路由
        if identity_kind == "id_or_title":
            song = library.get_by_id(identity) or library.get(identity)
        else:
            song = (library.get_by_id(identity)
                    if identity_kind == "id" else library.get(identity))
        if song is None:
            label = "歌曲 ID" if identity_kind == "id" else "歌曲"
            raise SongNotFound(f"未找到{label}：{identity}")
        return song

    def _save_and_report(
        self, snapshot, event_type: str, song: Song,
        *, meta: dict[str, Any] | None = None,
    ) -> None:
        self._songs.save(
            snapshot.value, expected_revision=snapshot.revision)
        event = {
            "schema_version": 2,
            "event_id": f"evt_{uuid.uuid4().hex}",
            "occurred_at": _normalize_timestamp(None),
            "recorded_at": datetime.now().astimezone().isoformat(
                timespec="seconds"),
            "type": event_type,
            "source": "songs-api",
            "song_id": song.id,
            "title_snapshot": song.title,
        }
        if meta is not None:
            event["meta"] = meta
        self._events.append(event)

    @staticmethod
    def _mutation(song: Song, library: SongLibrary) -> SongMutation:
        return SongMutation(
            song, library.count_active(), library.count_draft(),
            added=(),
        )


def _auto_section_from_title(title: str) -> int:
    """当 section=None 时，按标题字数自动计算 section (1..7)。

    规则与 grid-wrap _group 一致 (2026-07-30): 
    - 含英文字母的归 7 (长歌名/英文)
    - 中文按 len()， >6 归 7
    """
    if any(c.isascii() and c.isalpha() for c in title):
        return 7
    n = len(title.strip())
    return n if 1 <= n <= 6 else 7


def clean_song_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return _clean_song_fields(payload)
    except SongServiceError:
        raise
    except (TypeError, ValueError) as error:
        raise SongValidationFailed(str(error)) from error


def _clean_song_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in SongLibrary.EDITABLE_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if key in ("artists", "tags"):
            fields[key] = [
                str(item).strip() for item in (value or [])
                if str(item).strip()
            ]
        elif key == "capo":
            fields[key] = (
                None if value in (None, "")
                else max(0, min(12, int(value))))
        elif key == "section":
            if value in (None, ""):
                # 用户选了「自动(按字数)」— 存 None, 等 title 到位后延迟计算
                fields[key] = None
            else:
                fields[key] = max(1, min(7, int(value)))
        else:
            fields[key] = str(value).strip() if value is not None else ""
    if "title" in fields and not fields["title"]:
        raise SongValidationFailed("歌名不能为空")
    return fields


def song_values(song: Song) -> dict[str, Any]:
    return {
        "id": song.id, "title": song.title, "status": song.status,
        "section": song.section, "artists": song.artists,
        "lyricist": song.lyricist, "composer": song.composer,
        "key": song.key, "capo": song.capo,
        # R9.4 个人 Capo 库
        "capo_options": list(song.capo_options),
        "capo_default": song.capo_default,
        "difficulty": song.difficulty, "tabs": song.tabs,
        "tags": song.tags, "pinyin": song.pinyin,
        "added_at": song.added_at, "notes": song.notes,
        "learned_at": song.learned_at, "tab_files": song.tab_files,
        # R8 弹唱字段
        "lyrics_lrc": song.lyrics_lrc,
        "lyrics_plain": song.lyrics_plain,
        "audio_vocal_path": song.audio_vocal_path,
        "audio_instrumental_path": song.audio_instrumental_path,
        "audio_duration_ms": song.audio_duration_ms,
        # R9.6 软删除
        "deleted_at": song.deleted_at,
    }


# ── R8.1 辅助 ──

_AUDIO_MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


def _audio_mime(ext: str) -> str:
    """扩展名 → MIME；未知返 application/octet-stream。"""
    return _AUDIO_MIME_BY_EXT.get(ext.lower(), "application/octet-stream")
