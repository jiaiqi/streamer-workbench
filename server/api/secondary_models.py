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
    # M3 P2: 拖拽排序字段
    order_index: int | None = None
    # R1a.5：前端 CAS 自动保存所需的 revision（与服务端 sha256 hash 一致）
    revision: str = ""


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


# ── R1a.4 RenderDocument：POST /api/render/document 与 /api/export/document ──
# 预览与导出共享同一份 RenderDocument；接收 poster_id + 渲染参数，
# 由服务端解析 SongSource → SongSnapshot 列表 → 构造 RenderDocument。

class RenderDocumentRequest(StrictRequest):
    poster_id: str
    layout_id: str = "grid-wrap"          # P1 仅允许 grid-wrap
    theme_id: str = "海洋柔光"
    canvas_id: str = "9:20"
    page: int = 1
    parameters: dict = Field(default_factory=dict)


class RenderDocumentResponse(BaseModel):
    document_id: str
    poster_id: str
    layout_id: str
    theme_id: str
    canvas_id: str
    page: int
    pages_total: int
    song_count: int
    missing_song_ids: list[str] = Field(default_factory=list)
    page_policy_mode: str = "legacy-fixed-2"
    # 完整 RenderDocument JSON 用于客户端缓存/审计；体积可控（仅快照）
    document: dict = Field(default_factory=dict)


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


class ExportByIdsRequest(StrictRequest):
    """L2.2: 按 song_ids 列表批量导出，每首选中歌曲渲染成 1 张 PNG 存盘。"""
    theme: str
    song_ids: list[str] = Field(min_length=1)
    layout: str = "grid-wrap"
    canvas: str = "标准 9:16"
    avoid: bool = False


class ExportByIdsFileResponse(BaseModel):
    song_id: str
    title: str
    path: str
    filename: str
    duration_ms: float | None


class ExportByIdsResponse(BaseModel):
    ok: bool = True
    total: int = Field(ge=0)
    total_ms: float | None
    files: list[ExportByIdsFileResponse]


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


# ── R4.2.3 导出历史 ──────────────────────────────────────────────

class ExportLogEntryResponse(BaseModel):
    """GET /api/exports/recent - 单条导出历史。

    来源: events.jsonl 的 type=poster_exported 事件，按时间倒序返回。
    kind: "grid-export" (工作台批量/单页) | "live-poster" (直播复盘) | "learning-report" (学歌报告)
    """
    event_id: str
    occurred_at: str
    source: str
    kind: str
    subject: str
    count: int
    total_ms: float | None = None
    filename: str = ""
    output_dir: str = ""
    # 仅 live-poster 才有
    session_id: str = ""
    title: str = ""
    # 仅 learning-report 才有
    days: int = 0
    period_label: str = ""


class ExportLogRecentResponse(BaseModel):
    """GET /api/exports/recent 响应。"""
    items: list[ExportLogEntryResponse]


# ── R2 P3 直播会话 HTTP 模型 ────────────────────────────────────────

class LiveSessionCreateRequest(StrictRequest):
    """POST /api/live-sessions - 创建会话。"""
    rule_version: str = "rv1"
    title: str = ""
    poster_id: str | None = None


class LiveSessionSummary(BaseModel):
    """GET /api/live-sessions - 摘要。"""
    id: str
    state: str
    title: str
    rule_version: str
    started_at: str
    closed_at: str | None = None
    queue_size: int = 0


class LiveSessionDetail(BaseModel):
    """GET /api/live-sessions/{id} - 详情。"""
    id: str
    state: str
    title: str
    rule_version: str
    started_at: str
    closed_at: str | None = None
    poster_id: str | None = None
    notes: str = ""
    queue: list[dict] = Field(default_factory=list)
    performances: list[dict] = Field(default_factory=list)


class LiveSessionQueueRequest(StrictRequest):
    """POST /api/live-sessions/{id}/queue - 入队。"""
    requester_name: str
    requester_id: str | None = None
    song_id: str
    entitlement_id: str | None = None
    entitlement_kind: str = ""
    note: str = ""
    command_id: str | None = None


class LiveSessionQueueResponse(BaseModel):
    ok: bool = True
    request_id: str
    song_id: str
    position: int
    decision: dict
    duplicate_merged: bool = False


class LiveSessionRecordRequest(StrictRequest):
    """POST /api/live-sessions/{id}/record - 记录演唱结果。"""
    request_id: str
    result: str
    operator: str = "broadcaster"
    reason: str = ""


class LiveSessionRecordResponse(BaseModel):
    ok: bool = True
    request_id: str
    result: str
    refunded: bool = False
    refund_reason: str = ""


class LiveSessionEntitlementGrantRequest(StrictRequest):
    """POST /api/live-sessions/{id}/entitlements - 授予权益。"""
    kind: str
    rule_version: str = "rv1"
    quota: int = 1
    requester_id: str | None = None
    expires_at: str | None = None
    evidence_label: str = ""
    evidence_value: float | None = None
    platform_ref: str = ""


class LiveSessionEntitlementResponse(BaseModel):
    id: str
    kind: str
    rule_version: str
    requester_id: str | None
    quota: int
    consumed: int
    remaining: int
    granted_at: str
    expires_at: str | None = None


class LiveSessionPosterRequest(StrictRequest):
    """R2.5: POST /api/live-sessions/{id}/poster - 渲染直播复盘海报。

    library 是 LiveSessionSnapshot（不通过 SongLibrary），所以不传 song_ids；
    只传 theme/canvas/parameters 走 live-set 自己的 ParamSpec。
    """
    theme_id: str = "海洋柔光"
    canvas_id: str = "抖音全屏 9:20"
    parameters: dict = Field(default_factory=dict)


class LearningReportPosterRequest(StrictRequest):
    """R3.5: POST /api/learning-report/poster - 渲染学歌报告海报。

    走 StatsApplicationService 事件聚合 + LearningReportSnapshot 数据通道，
    跟 live-set 一样绕开 SongLibrary 路径（learning-report 输入是事件流，
    不是曲库快照）。

    R4.0 收紧范围：days ∈ [1, 365]，top_n_artists ∈ [1, 20]，
    越界由 Pydantic 422 直接拒绝，避免服务内部被异常值拖死。
    """
    theme_id: str = "海洋柔光"
    canvas_id: str = "抖音全屏 9:20"
    period_label: str = ""           # "2026 年 7 月"；空 → 自动 "近 N 天"
    days: int = Field(30, ge=1, le=365)            # 时间窗口 (1 天 ~ 1 年)
    top_n_artists: int = Field(5, ge=1, le=20)     # 歌手 Top N (1 ~ 20)


# ── P4 R2 学歌练习 HTTP 模型 ───────────────────────────────────

class PracticeLogRequest(StrictRequest):
    """POST /api/practice/log — 打卡。"""
    song_id: str = ""
    title_snapshot: str = ""
    minutes: int = 1
    self_rating: int = 0
    note: str = ""
    occurred_at: str = ""
    event_id: str = ""


class PracticeLogResponse(BaseModel):
    ok: bool = True
    event_id: str
    already_processed: bool = False
    minutes: int
    self_rating: int
    note: str = ""
    title_snapshot: str = ""


class PracticeStatsResponse(BaseModel):
    total_minutes: int
    total_sessions: int
    current_streak_days: int
    longest_streak_days: int
    last_30_days: int
    songs_practiced: int
    top_practiced: list[dict] = Field(default_factory=list)
    month_current_minutes: int = 0
    month_current_sessions: int = 0
    months: list[dict] = Field(default_factory=list)


class PracticeStreakResponse(BaseModel):
    current_streak: int
    longest_streak: int
    total_days: int
    first_date: str = ""
    last_date: str = ""


class PracticeMonthSummaryResponse(BaseModel):
    month: str
    total_minutes: int
    total_sessions: int
    unique_songs: int
    rated_count: int
    rating_avg: float = 0.0


# ── P2 R4: 排版参数面板契约 (ParamSpec) ──────────────────────────
# 镜像 core/layouts/base.py::ParamSpec；UI 据此动态生成 Inspector 控件。
# kind 取值: "int" | "float" | "bool" | "select" | "section_map" | "group_order"

ParamSpecKind = Literal[
    "int", "float", "bool", "select", "section_map", "group_order",
]


class ParamSpecResponse(BaseModel):
    """单个可调参数描述。"""
    key: str
    label: str
    kind: ParamSpecKind
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[Any] | None = None
    group: str = "布局"
    help: str = ""
    section_axis: str | None = None
    unit: str = ""


# ===== R3 Discovery =====

class DiscoveryItem(BaseModel):
    song_id: str
    title: str
    artist: str = ""
    difficulty: str = ""
    key: str = ""
    capo: int | None = 0
    last_learned_at: str = ""
    last_requested_at: str = ""
    last_performed_at: str = ""
    practice_count: int = 0
    request_count: int = 0
    perform_count: int = 0
    reason: str = ""


class DiscoveryResponse(BaseModel):
    items: list[DiscoveryItem] = Field(default_factory=list)
    note: str = ""


# ===== R4 Stats =====

class OverviewStatsResponse(BaseModel):
    total_songs: int
    active_songs: int
    draft_songs: int
    total_events: int
    events_by_type: dict[str, int] = Field(default_factory=dict)
    total_practice_minutes: int = 0
    total_practice_sessions: int = 0
    current_streak_days: int = 0
    longest_streak_days: int = 0
    total_queue_requests: int = 0
    total_performances: int = 0
    total_posters_exported: int = 0
    note: str = ""


class FeedItemResponse(BaseModel):
    event_id: str
    occurred_at: str
    type: str
    source: str
    song_id: str = ""
    title_snapshot: str = ""
    meta: dict = Field(default_factory=dict)
    summary: str = ""


class FeedResponse(BaseModel):
    items: list[FeedItemResponse] = Field(default_factory=list)
    note: str = ""


class TopSongItemResponse(BaseModel):
    song_id: str
    title: str
    artist: str = ""
    count: int = 0
    minutes: int = 0


class TopSongsResponse(BaseModel):
    metric: str
    items: list[TopSongItemResponse] = Field(default_factory=list)
    note: str = ""


class RequestedSongItemResponse(BaseModel):
    """M2.5: 点歌热度 Top N（含最近一次点歌时间）"""
    song_id: str
    title: str
    artist: str = ""
    count: int = 0
    last_requested: str = ""  # ISO datetime


class RecentlySungItemResponse(BaseModel):
    """M2.5: 最近演唱 Top N（按时间倒序）"""
    song_id: str
    title: str
    artist: str = ""
    last_sung: str = ""  # ISO datetime
    times_sung: int = 0


class InsightsResponse(BaseModel):
    """M2.5: 综合洞察 — 点歌热度 + 最近演唱"""
    top_requested: list[RequestedSongItemResponse] = Field(default_factory=list)
    recently_sung: list[RecentlySungItemResponse] = Field(default_factory=list)
    note: str = ""


class DistributionBucketResponse(BaseModel):
    label: str
    count: int


class DistributionResponse(BaseModel):
    metric: str
    buckets: list[DistributionBucketResponse] = Field(default_factory=list)
    note: str = ""


# ── R8.1 弹唱：音频 + 播放事件 ──


class AudioUploadResponse(BaseModel):
    """POST /api/songs/{id}/audio 响应。"""
    ok: bool = True
    song_id: str
    role: str                                  # "vocal" | "instrumental"
    filename: str
    path: str                                  # 相对 data/ 的路径（"audio/.../vocal.mp3"）


class AudioItemResponse(BaseModel):
    """GET /api/songs/{id}/audio/list 单条。"""
    role: str                                  # "vocal" | "instrumental" | "unknown"
    filename: str
    path: str
    mime: str = "application/octet-stream"


class AudioListResponse(BaseModel):
    """GET/DELETE /api/songs/{id}/audio/list 响应。"""
    song_id: str
    items: list[AudioItemResponse] = Field(default_factory=list)


class AudioStreamInfo(BaseModel):
    """GET /api/songs/{id}/audio/{role} 元信息响应。"""
    song_id: str
    role: str
    filename: str
    path: str
    size: int = 0
    mime: str = "application/octet-stream"


class PlaybackEventRequest(StrictRequest):
    """POST /api/playback/events — 上报播放事件。

    复用 events.jsonl：type=playback_started/paused/completed，
    写到 meta 字段里携带业务数据。
    """
    type: str                                  # "playback_started" | "playback_paused" | "playback_completed"
    song_id: str
    source: str | None = None                 # "vocal" | "instrumental" | None
    position_ms: int = 0
    duration_ms: int = 0
    occurred_at: str = ""                     # ISO；空则用服务端 now


class PlaybackEventResponse(BaseModel):
    ok: bool = True
    type: str


# L2.3 快照：列出 / 恢复
class SnapshotItemResponse(BaseModel):
    filename: str
    size_bytes: int
    modified_at: str  # ISO


class SnapshotListResponse(BaseModel):
    total: int
    items: list[SnapshotItemResponse]


class SnapshotRestoreRequest(StrictRequest):
    filename: str


class SnapshotRestoreResponse(BaseModel):
    ok: bool = True
    filename: str


# M2.7+ 在线元数据响应模型


class MetadataHitResponse(BaseModel):
    """搜索结果条目（轻量）。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    song_id: str
    title: str
    artist: str
    album: str | None = None
    duration_ms: int | None = None
    cover_url: str | None = None


class MetadataSongDetailResponse(BaseModel):
    """歌曲详情。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    song_id: str
    title: str
    artist: str
    artist_id: str | None = None
    album: str | None = None
    album_id: str | None = None
    duration_ms: int = 0
    cover_url: str | None = None
    bpm: float | None = None


class MetadataLyricResponse(BaseModel):
    """LRC 歌词。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    song_id: str
    lrc_text: str
    translated_lrc: str | None = None


class MetadataArtistResponse(BaseModel):
    """艺人详情（含热门歌曲）。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    artist_id: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    songs: list[MetadataHitResponse] = []


class MetadataAlbumResponse(BaseModel):
    """专辑详情。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    album_id: str
    title: str
    artist: str
    cover_url: str | None = None
    release_date: str | None = None
    songs: list[MetadataHitResponse] = []


class MetadataPlaylistResponse(BaseModel):
    """歌单详情。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    playlist_id: str
    title: str
    creator: str | None = None
    cover_url: str | None = None
    description: str | None = None
    play_count: int | None = None
    songs: list[MetadataHitResponse] = []


class MetadataChartResponse(BaseModel):
    """榜单条目。"""
    model_config = ConfigDict(extra="forbid")
    source: str
    chart_id: str
    title: str
    cover_url: str | None = None
    description: str | None = None


class MetadataSearchResponse(BaseModel):
    """搜索结果。"""
    model_config = ConfigDict(extra="forbid")
    keyword: str
    type: str
    provider: str | None = None  # 命中的 provider（缓存可为空）
    items: list[MetadataHitResponse] = []


class MetadataProviderListResponse(BaseModel):
    """当前 router 注册的 providers。"""
    model_config = ConfigDict(extra="forbid")
    providers: list[str]


# ── LiveSession M2.4 点歌条件 ──


class RequestPolicyResponse(BaseModel):
    """GET /api/live-sessions/{id}/policy - 当前会话 RequestPolicy。"""
    model_config = ConfigDict(extra="forbid")
    rule_version: str
    created_at: str
    fan_join_session_quota: int
    member_daily_quota: int
    gift_exchange_quota: int
    high_value_gift_names: list[str] = Field(default_factory=list)
    bump_default_target: int
    bump_requires_broadcaster: bool
    fairness_max_consecutive_bumps: int
    entitlement_session_window_hours: int
    # M2.4
    cooldown_seconds_per_user: int = 0
    max_queue_length: int = 0
    per_song_max_per_session: int = 0
    per_user_max_in_queue: int = 0


class RequestPolicyUpdateRequest(StrictRequest):
    """POST /api/live-sessions/{id}/policy - 主播更新点歌条件。

    M2.4：只暴露 4 个运营字段（quota / 插队 / 公平保护等"业务规则"不开放给主播 UI 改）。
    0 = 不限；非 0 必须 >= 1。
    """
    cooldown_seconds_per_user: int = Field(default=0, ge=0)
    max_queue_length: int = Field(default=0, ge=0)
    per_song_max_per_session: int = Field(default=0, ge=0)
    per_user_max_in_queue: int = Field(default=0, ge=0)


# ── M2.2 WebDAV 同步 ─────────────────────────────────────────────

class WebDavConfigResponse(BaseModel):
    """GET /api/backup/webdav/config - 脱敏返回的当前配置。"""
    model_config = ConfigDict(extra="forbid")
    configured: bool
    url: str = ""
    username: str = ""
    remote_dir: str = ""
    updated_at: str = ""
    needs_unlock: bool = False


class WebDavConfigSaveRequest(StrictRequest):
    """PUT /api/backup/webdav/config - 保存/更新 WebDAV 配置。

    master_password：settings 主密码（用于加密）。
    password：WebDAV 服务密码（明文传输 + 服务端加密存）。
    """
    url: str
    username: str = ""
    password: str = ""
    remote_dir: str
    master_password: str


class WebDavConfigSaveResponse(BaseModel):
    ok: bool = True
    updated_at: str


class WebDavClearRequest(StrictRequest):
    master_password: str


class WebDavTestRequest(StrictRequest):
    """POST /api/backup/webdav/test - 用临时凭证测试连接（不写盘）。"""
    url: str
    username: str = ""
    password: str = ""


class WebDavTestResponse(BaseModel):
    ok: bool
    status: int = 0
    message: str


class WebDavMasterRequest(StrictRequest):
    """list / push / pull / test-remote 都需要 master_password 解锁。"""
    master_password: str
    remote_name: str | None = None  # 仅 pull 使用


class WebDavRemoteFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    href: str
    size: int
    last_modified: str


class WebDavRemoteListResponse(BaseModel):
    files: list[WebDavRemoteFile] = Field(default_factory=list)


class WebDavPushResponse(BaseModel):
    ok: bool = True
    remote_path: str
    remote_name: str
    file_count: int
    total_bytes: int


class WebDavPullResponse(BaseModel):
    ok: bool = True
    remote_name: str
    manifest: dict = Field(default_factory=dict)


# ── M3 海报 UI/UX（P0 缩略图 + 重命名 + 复制） ──────────────────────────

class NamePatchRequest(StrictRequest):
    """PATCH /api/posters/{id}/name - inline 重命名。

    revision 可选：客户端应传当前 revision 以触发 CAS；
    不传则用 last-known 覆盖（不推荐但允许向前兼容）。
    """
    name: str = Field(..., min_length=1, max_length=200)
    revision: str | None = None


# ── M3 海报 UI/UX（P1 批量操作） ────────────────────────────────────

from typing import Literal  # noqa: E402  (位置无副作用)


class PosterBatchRequest(StrictRequest):
    """POST /api/posters/batch - 批量操作。

    action:
    - delete: 删除 ids 中所有海报
    - duplicate: 复制 ids 中所有海报（新 id + 「(副本)」名称）
    - set_theme: 把 ids 中所有海报的 theme_id 改为 theme
    - reorder: 按 ids 数组顺序写入每个 poster 的 order_index（M3 P2 拖拽排序）
      — ids 必须是当前所有未删除 poster 的子集；服务端按数组下标分配 order_index
      — 数组外的 poster 保持原 order_index（不会重排整库）

    ids 非空，且元素必须是合法 poster_id（避免 path traversal）。
    """
    action: Literal["delete", "duplicate", "set_theme", "reorder"]
    ids: list[str] = Field(..., min_length=1, max_length=200)
    # set_theme 时必填；其他 action 忽略
    theme: str | None = None


# ── M2.4 WebDAV 自动同步 ────────────────────────────────────

class AutoSyncSettingsRequest(StrictRequest):
    """POST /api/backup/webdav/auto-sync - 启用 / 关闭 / 调间隔 / 调方向。

    全部字段 optional；只更新传入的字段。
    enabled=true 时必须同时提供 master_password（用于 scheduler 内部解锁）。
    """
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    direction: Literal["push", "pull", "both"] | None = None
    master_password: str | None = None


class AutoSyncRunRequest(StrictRequest):
    """POST /api/backup/webdav/auto-sync/run - 立即触发一次同步。"""
    master_password: str = Field(..., min_length=1, max_length=200)
