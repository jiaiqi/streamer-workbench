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


# ── R1a.1 Poster ──
# 严格模型：每个字段都给出；未知字段前端会被 Pydantic 拒收，
# 防御未来 schema 漂移。Poster 的范围保护（仅 grid-wrap + legacy-fixed-2）
# 由 service.validate() 完成；这里只做传输形校验。

class PosterSongSource(BaseModel):
    type: str  # all_active | manual | artist
    artists: list[str] = Field(default_factory=list)


class PosterPagePolicy(BaseModel):
    mode: str = "legacy-fixed-2"
    min_pages: int | None = None
    max_pages: int | None = None
    manual_pages: list[dict] = Field(default_factory=list)


class PosterExportSettings(BaseModel):
    format: str = "png"          # png | jpeg
    jpeg_quality: int = 92
    single_page: bool = False
    dpi: int = 144


class PosterRequest(StrictRequest):
    """创建或完整更新海报载荷。

    所有字段必填；省略会触发 Pydantic 校验，可保证 service 收不到
    不完整数据。范围保护由 service 强制。
    """
    id: str = ""                # 创建：可空，service 自动生成；更新：必填已存在 id
    name: str
    song_source: PosterSongSource
    selected_song_ids: list[str] = Field(default_factory=list)
    grouping: str = "none"
    sorting: str = "manual"
    layout_id: str = "grid-wrap"
    theme_id: str = "海洋柔光"
    canvas_id: str = "9:20"
    page_policy: PosterPagePolicy = Field(default_factory=PosterPagePolicy)
    parameters: dict = Field(default_factory=dict)
    export_settings: PosterExportSettings = Field(default_factory=PosterExportSettings)
    # 可选引用关系；不影响持久化生命周期
    optional_session_ref: str | None = None


class PosterResponse(PosterRequest):
    schema_version: int = 1
    id: str
    created_at: str = ""
    updated_at: str = ""


class PosterSummaryResponse(BaseModel):
    id: str
    name: str
    layout_id: str
    theme_id: str
    canvas_id: str
    created_at: str
    updated_at: str
    song_count: int


class PosterSaveResponse(BaseModel):
    ok: bool = True
    id: str
    revision: str
    updated_at: str


class PosterResolveSong(BaseModel):
    id: str
    title: str
    artists: list[str]
    section: int


class PosterResolveResponse(BaseModel):
    poster_id: str
    songs: list[PosterResolveSong]
    missing_song_ids: list[str]


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
