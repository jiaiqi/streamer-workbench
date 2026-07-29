"""Songs API 的显式请求与成功响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SongEditableFields(StrictRequest):
    title: Any | None = None
    artists: list[Any] | None = None
    lyricist: Any | None = None
    composer: Any | None = None
    key: Any | None = None
    capo: Any | None = None
    difficulty: Any | None = None
    tabs: Any | None = None
    tags: list[Any] | None = None
    pinyin: Any | None = None
    notes: Any | None = None
    section: Any | None = None


class SongCreateRequest(SongEditableFields):
    status: str | None = None


class SongLegacyUpdateRequest(StrictRequest):
    title: str
    fields: SongEditableFields


class SongLegacyIdentityRequest(StrictRequest):
    title: str


class SongStatusRequest(StrictRequest):
    status: str


class SongLegacyStatusRequest(SongStatusRequest):
    title: str


class SongResponse(BaseModel):
    id: str
    title: str
    status: str
    section: int | None
    artists: list[str]
    lyricist: str
    composer: str
    key: str
    capo: int | None
    difficulty: str
    tabs: str
    tags: list[str]
    pinyin: str
    added_at: str
    notes: str
    learned_at: str
    tab_files: list[str]


class SongCounts(BaseModel):
    active: int = Field(ge=0)
    draft: int = Field(ge=0)


class SongsSummaryResponse(BaseModel):
    total: int = Field(ge=0)
    by_len: dict[str, int]


class SongsListResponse(SongCounts):
    total: int = Field(ge=0)
    songs: list[SongResponse]


class SongUpdateResponse(BaseModel):
    ok: bool = True
    song: SongResponse


class SongMutationResponse(SongUpdateResponse, SongCounts):
    pass


class SongLegacyStatusResponse(SongCounts):
    ok: bool = True
    title: str
    status: str


class SongLegacyDeleteResponse(SongCounts):
    ok: bool = True
    title: str


class SongDeleteResponse(SongCounts):
    ok: bool = True
    song_id: str
    title_snapshot: str
