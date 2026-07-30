"""Settings、Preset、Render 与 Export 的 HTTP 边界模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsUpdateRequest(StrictRequest):
    output_dir: str | None = None
    default_canvas: str | None = None
    default_theme: str | None = None
    font_path: str | None = None
    backup_count: int | None = None
    render_threads: int | None = None
    appearanceMode: Literal["system", "light", "dark"] | None = None
    applicationAccentId: Literal[
        "bambooMoon", "rainSky", "distantMountain", "rouge",
        "begonia", "wisteria", "amber", "pineFlower",
    ] | None = None


class SettingsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    output_dir: str
    default_canvas: str
    default_theme: str
    font_path: str
    backup_count: int
    render_threads: int
    appearanceMode: Literal["system", "light", "dark"] = "system"
    applicationAccentId: Literal[
        "bambooMoon", "rainSky", "distantMountain", "rouge",
        "begonia", "wisteria", "amber", "pineFlower",
    ] = "bambooMoon"


class SettingsUpdateResponse(BaseModel):
    ok: bool = True
    settings: SettingsResponse


class DataDirStatusResponse(BaseModel):
    current: str
    source: str
    source_label: str
    startup_config: str
    platform_default: str | None = None
    pinned: bool = False


class DataDirInspectRequest(StrictRequest):
    path: str


class DataDirInspectResponse(BaseModel):
    path: str
    valid: bool
    message: str = ""
    exists: bool = False
    is_current: bool = False
    parent_writable: bool = False
    has_existing_data: bool = False
    existing_items: list[str] = Field(default_factory=list)
    will_initialize: bool = False


class DataDirSwitchRequest(StrictRequest):
    path: str
    migrate: bool = False
    use_existing: bool = False


class DataDirSwitchResponse(BaseModel):
    ok: bool = True
    data_root: str
    startup_config: str
    requires_restart: bool = True
    migrated: list[str] = Field(default_factory=list)
    used_existing: bool = False


class SongQueryRequest(StrictRequest):
    status: str = "active"
    classify: str = "chars"
    sort_by: str = "default"
    max_songs: int = 0
    custom_ids: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class PresetRequest(StrictRequest):
    schema_version: int = 2
    id: str = ""
    name: str = "未命名预设"
    created_at: str = ""
    updated_at: str = ""
    is_default: bool = False
    song_query: SongQueryRequest = Field(default_factory=SongQueryRequest)
    layout_id: str = "grid-wrap"
    palette_id: str = ""
    skin_id: str = ""
    canvas: dict[str, Any] = Field(default_factory=lambda: {"width": 1080, "height": 2400})
    params: dict[str, Any] = Field(default_factory=dict)
    export: dict[str, Any] = Field(default_factory=dict)
    color_overrides: dict[str, Any] = Field(default_factory=dict)


class PresetResponse(PresetRequest):
    pass


class PresetSummaryResponse(BaseModel):
    id: str
    name: str
    layout_id: str
    is_default: bool
    created_at: str
    updated_at: str


class PresetSaveResponse(BaseModel):
    ok: bool = True
    id: str
    updated_at: str


class PresetDuplicateRequest(StrictRequest):
    name: str = ""


class PresetDuplicateResponse(BaseModel):
    ok: bool = True
    id: str
    name: str


class PresetDefaultResponse(BaseModel):
    ok: bool = True
    id: str


class OkResponse(BaseModel):
    ok: bool = True


class RenderRequest(StrictRequest):
    theme: str
    page: int = 1
    canvas: str = "标准 9:16"
    avoid: bool = False
    layout: str = "grid-wrap"
    margin: int | None = None
    font_song: int | None = None
    row_h: int | None = None
    sec_gap: int | None = None
    # 旧前端用于强制刷新浏览器图片缓存；不参与渲染语义。
    t: str | None = None


class ExportRequest(RenderRequest):
    pass


class ExportBatchRequest(StrictRequest):
    layout: str = "grid-wrap"
    canvas: str = "抖音全屏 9:20"
    avoid: bool = True


class ExportResponse(BaseModel):
    ok: bool = True
    path: str
    filename: str
    duration_ms: float | None


class ExportBatchResponse(BaseModel):
    ok: bool = True
    job_id: str
    total: int = Field(ge=0)


class ExportedFileResponse(BaseModel):
    theme: str
    page: int
    path: str


class ExportJobResponse(BaseModel):
    status: Literal["running", "done", "error", "cancelled"]
    done: int = Field(ge=0)
    total: int = Field(ge=0)
    current: str
    files: list[ExportedFileResponse]
    output_dir: str
    total_ms: float | None
    error: str | None


class ExportOpenResponse(BaseModel):
    ok: bool = True
    output_dir: str
