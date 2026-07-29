"""歌曲写用例：以不可变 ID 为主，并集中协调 Repository 与事件。"""

from __future__ import annotations

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
        current = library.get_by_id(song.id)
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
        snapshot = self._songs.load()
        library = snapshot.value
        song = self._find(library, identity_kind, identity)
        library.remove_by_id(song.id)
        self._save_and_report(snapshot, "song_deleted", song)
        return SongDeletion(
            song.id, song.title, library.count_active(), library.count_draft())

    @staticmethod
    def _find(library: SongLibrary, identity_kind: str, identity: str) -> Song:
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
            song, library.count_active(), library.count_draft())


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
            fields[key] = (
                None if value in (None, "")
                else max(1, min(7, int(value))))
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
        "difficulty": song.difficulty, "tabs": song.tabs,
        "tags": song.tags, "pinyin": song.pinyin,
        "added_at": song.added_at, "notes": song.notes,
        "learned_at": song.learned_at, "tab_files": song.tab_files,
    }
