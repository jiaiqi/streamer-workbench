"""R0.8 first typed Event request/response models."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EventReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["queue_added", "song_sung", "practice_logged"]
    event_id: str | None = None
    song_id: str | None = None
    title_snapshot: str | None = None
    occurred_at: str | None = None
    source: str | None = None
    meta: dict[str, Any] | None = None
    title: str | None = None
    ts: str | None = None


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str
    schema_version: int | None = None
    event_id: str | None = None
    occurred_at: str | None = None
    recorded_at: str | None = None
    source: str | None = None


class EventReportResponse(BaseModel):
    ok: bool = True
    event: EventRecord


class EventsResponse(BaseModel):
    total: int = Field(ge=0)
    events: list[EventRecord]
