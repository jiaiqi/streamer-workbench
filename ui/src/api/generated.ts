// 此文件由 tools/generate_api_types.py 生成，请勿手工修改。
// OpenAPI JSON 是临时中间产物；本文件随源码提交。

export interface AnalyzeQuery {
  "canvas_id"?: string;
  "grouping"?: string;
  "parameters"?: Record<string, unknown>;
  "poster_id"?: string | null;
  "song_ids"?: Array<string> | null;
  "theme_id"?: string;
}

export interface AudioItemResponse {
  "filename": string;
  "mime"?: string;
  "path": string;
  "role": string;
  [key: string]: unknown;
}

export interface AudioListResponse {
  "items"?: Array<AudioItemResponse>;
  "song_id": string;
  [key: string]: unknown;
}

export interface AudioStreamInfo {
  "filename": string;
  "mime"?: string;
  "path": string;
  "role": string;
  "size"?: number;
  "song_id": string;
  [key: string]: unknown;
}

export interface AudioUploadResponse {
  "filename": string;
  "ok"?: boolean;
  "path": string;
  "role": string;
  "song_id": string;
  [key: string]: unknown;
}

export interface Body_api_audio_upload_api_songs__identity__audio_post {
  "file": string;
  [key: string]: unknown;
}

export interface Body_api_tab_upload_api_songs__identity__tabs_post {
  "file": string;
  [key: string]: unknown;
}

export interface DataDirInspectRequest {
  "path": string;
}

export interface DataDirInspectResponse {
  "existing_items"?: Array<string>;
  "exists"?: boolean;
  "has_existing_data"?: boolean;
  "is_current"?: boolean;
  "message"?: string;
  "parent_writable"?: boolean;
  "path": string;
  "valid": boolean;
  "will_initialize"?: boolean;
  [key: string]: unknown;
}

export interface DataDirStatusResponse {
  "current": string;
  "pinned"?: boolean;
  "platform_default"?: string | null;
  "source": string;
  "source_label": string;
  "startup_config": string;
  [key: string]: unknown;
}

export interface DataDirSwitchRequest {
  "migrate"?: boolean;
  "path": string;
  "use_existing"?: boolean;
}

export interface DataDirSwitchResponse {
  "data_root": string;
  "migrated"?: Array<string>;
  "ok"?: boolean;
  "requires_restart"?: boolean;
  "startup_config": string;
  "used_existing"?: boolean;
  [key: string]: unknown;
}

export interface DiscoveryItem {
  "artist"?: string;
  "capo"?: number | null;
  "difficulty"?: string;
  "key"?: string;
  "last_learned_at"?: string;
  "last_performed_at"?: string;
  "last_requested_at"?: string;
  "perform_count"?: number;
  "practice_count"?: number;
  "reason"?: string;
  "request_count"?: number;
  "song_id": string;
  "title": string;
  [key: string]: unknown;
}

export interface DiscoveryResponse {
  "items"?: Array<DiscoveryItem>;
  "note"?: string;
  [key: string]: unknown;
}

export interface DistributionBucketResponse {
  "count": number;
  "label": string;
  [key: string]: unknown;
}

export interface DistributionResponse {
  "buckets"?: Array<DistributionBucketResponse>;
  "metric": string;
  "note"?: string;
  [key: string]: unknown;
}

export interface EventRecord {
  "event_id"?: string | null;
  "occurred_at"?: string | null;
  "recorded_at"?: string | null;
  "schema_version"?: number | null;
  "source"?: string | null;
  "type": string;
  [key: string]: unknown;
}

export interface EventReportRequest {
  "event_id"?: string | null;
  "meta"?: Record<string, unknown> | null;
  "occurred_at"?: string | null;
  "song_id"?: string | null;
  "source"?: string | null;
  "title"?: string | null;
  "title_snapshot"?: string | null;
  "ts"?: string | null;
  "type": "queue_added" | "song_sung" | "practice_logged";
}

export interface EventReportResponse {
  "event": EventRecord;
  "ok"?: boolean;
  [key: string]: unknown;
}

export interface EventsResponse {
  "events": Array<EventRecord>;
  "total": number;
  [key: string]: unknown;
}

export interface ExportBatchResponse {
  "job_id": string;
  "ok"?: boolean;
  "total": number;
  [key: string]: unknown;
}

export interface ExportJobResponse {
  "current": string;
  "done": number;
  "error": string | null;
  "files": Array<ExportedFileResponse>;
  "output_dir": string;
  "status": "running" | "done" | "error" | "cancelled";
  "total": number;
  "total_ms": number | null;
  [key: string]: unknown;
}

export interface ExportLogEntryResponse {
  "count": number;
  "days"?: number;
  "event_id": string;
  "filename"?: string;
  "kind": string;
  "occurred_at": string;
  "output_dir"?: string;
  "period_label"?: string;
  "session_id"?: string;
  "source": string;
  "subject": string;
  "title"?: string;
  "total_ms"?: number | null;
  [key: string]: unknown;
}

export interface ExportLogRecentResponse {
  "items": Array<ExportLogEntryResponse>;
  [key: string]: unknown;
}

export interface ExportOpenResponse {
  "ok"?: boolean;
  "output_dir": string;
  [key: string]: unknown;
}

export interface ExportResponse {
  "duration_ms": number | null;
  "filename": string;
  "ok"?: boolean;
  "path": string;
  [key: string]: unknown;
}

export interface ExportedFileResponse {
  "page": number;
  "path": string;
  "theme": string;
  [key: string]: unknown;
}

export interface FeedItemResponse {
  "event_id": string;
  "meta"?: Record<string, unknown>;
  "occurred_at": string;
  "song_id"?: string;
  "source": string;
  "summary"?: string;
  "title_snapshot"?: string;
  "type": string;
  [key: string]: unknown;
}

export interface FeedResponse {
  "items"?: Array<FeedItemResponse>;
  "note"?: string;
  [key: string]: unknown;
}

export interface HTTPValidationError {
  "detail"?: Array<ValidationError>;
  [key: string]: unknown;
}

export interface InsightsResponse {
  "note"?: string;
  "recently_sung"?: Array<RecentlySungItemResponse>;
  "top_requested"?: Array<RequestedSongItemResponse>;
  [key: string]: unknown;
}

export interface LearningReportPosterRequest {
  "canvas_id"?: string;
  "days"?: number;
  "period_label"?: string;
  "theme_id"?: string;
  "top_n_artists"?: number;
}

export interface LiveSessionCreateRequest {
  "poster_id"?: string | null;
  "rule_version"?: string;
  "title"?: string;
}

export interface LiveSessionDetail {
  "closed_at"?: string | null;
  "id": string;
  "notes"?: string;
  "performances"?: Array<Record<string, unknown>>;
  "poster_id"?: string | null;
  "queue"?: Array<Record<string, unknown>>;
  "rule_version": string;
  "started_at": string;
  "state": string;
  "title": string;
  [key: string]: unknown;
}

export interface LiveSessionEntitlementGrantRequest {
  "evidence_label"?: string;
  "evidence_value"?: number | null;
  "expires_at"?: string | null;
  "kind": string;
  "platform_ref"?: string;
  "quota"?: number;
  "requester_id"?: string | null;
  "rule_version"?: string;
}

export interface LiveSessionEntitlementResponse {
  "consumed": number;
  "expires_at"?: string | null;
  "granted_at": string;
  "id": string;
  "kind": string;
  "quota": number;
  "remaining": number;
  "requester_id": string | null;
  "rule_version": string;
  [key: string]: unknown;
}

export interface LiveSessionPosterRequest {
  "canvas_id"?: string;
  "parameters"?: Record<string, unknown>;
  "theme_id"?: string;
}

export interface LiveSessionQueueRequest {
  "command_id"?: string | null;
  "entitlement_id"?: string | null;
  "entitlement_kind"?: string;
  "note"?: string;
  "requester_id"?: string | null;
  "requester_name": string;
  "song_id": string;
}

export interface LiveSessionQueueResponse {
  "decision": Record<string, unknown>;
  "duplicate_merged"?: boolean;
  "ok"?: boolean;
  "position": number;
  "request_id": string;
  "song_id": string;
  [key: string]: unknown;
}

export interface LiveSessionRecordRequest {
  "operator"?: string;
  "reason"?: string;
  "request_id": string;
  "result": string;
}

export interface LiveSessionRecordResponse {
  "ok"?: boolean;
  "refund_reason"?: string;
  "refunded"?: boolean;
  "request_id": string;
  "result": string;
  [key: string]: unknown;
}

export interface LiveSessionSummary {
  "closed_at"?: string | null;
  "id": string;
  "queue_size"?: number;
  "rule_version": string;
  "started_at": string;
  "state": string;
  "title": string;
  [key: string]: unknown;
}

export interface OkResponse {
  "ok"?: boolean;
  [key: string]: unknown;
}

export interface OverviewStatsResponse {
  "active_songs": number;
  "current_streak_days"?: number;
  "draft_songs": number;
  "events_by_type"?: Record<string, number>;
  "longest_streak_days"?: number;
  "note"?: string;
  "total_events": number;
  "total_performances"?: number;
  "total_posters_exported"?: number;
  "total_practice_minutes"?: number;
  "total_practice_sessions"?: number;
  "total_queue_requests"?: number;
  "total_songs": number;
  [key: string]: unknown;
}

export interface ParamSpecResponse {
  "choices"?: Array<unknown> | null;
  "default"?: unknown;
  "group"?: string;
  "help"?: string;
  "key": string;
  "kind": "int" | "float" | "bool" | "select" | "section_map" | "group_order";
  "label": string;
  "max"?: number | null;
  "min"?: number | null;
  "section_axis"?: string | null;
  "step"?: number | null;
  "unit"?: string;
  [key: string]: unknown;
}

export interface PlaybackEventRequest {
  "duration_ms"?: number;
  "occurred_at"?: string;
  "position_ms"?: number;
  "song_id": string;
  "source"?: string | null;
  "type": string;
}

export interface PlaybackEventResponse {
  "ok"?: boolean;
  "type": string;
  [key: string]: unknown;
}

export interface PosterExportSettings {
  "dpi"?: number;
  "format"?: string;
  "jpeg_quality"?: number;
  "single_page"?: boolean;
  [key: string]: unknown;
}

export interface PosterPagePolicy {
  "manual_pages"?: Array<Record<string, unknown>>;
  "max_pages"?: number | null;
  "min_pages"?: number | null;
  "mode"?: string;
  [key: string]: unknown;
}

export interface PosterRequest {
  "canvas_id"?: string;
  "export_settings"?: PosterExportSettings;
  "grouping"?: string;
  "id"?: string;
  "layout_id"?: string;
  "name": string;
  "optional_session_ref"?: string | null;
  "page_policy"?: PosterPagePolicy;
  "parameters"?: Record<string, unknown>;
  "selected_song_ids"?: Array<string>;
  "song_source": PosterSongSource;
  "sorting"?: string;
  "theme_id"?: string;
}

export interface PosterResolveResponse {
  "missing_song_ids": Array<string>;
  "poster_id": string;
  "songs": Array<PosterResolveSong>;
  [key: string]: unknown;
}

export interface PosterResolveSong {
  "artists": Array<string>;
  "id": string;
  "section": number;
  "title": string;
  [key: string]: unknown;
}

export interface PosterResponse {
  "canvas_id"?: string;
  "created_at"?: string;
  "export_settings"?: PosterExportSettings;
  "grouping"?: string;
  "id": string;
  "layout_id"?: string;
  "name": string;
  "optional_session_ref"?: string | null;
  "page_policy"?: PosterPagePolicy;
  "parameters"?: Record<string, unknown>;
  "revision"?: string;
  "schema_version"?: number;
  "selected_song_ids"?: Array<string>;
  "song_source": PosterSongSource;
  "sorting"?: string;
  "theme_id"?: string;
  "updated_at"?: string;
}

export interface PosterSaveResponse {
  "id": string;
  "ok"?: boolean;
  "revision": string;
  "updated_at": string;
  [key: string]: unknown;
}

export interface PosterSongSource {
  "artists"?: Array<string>;
  "type": string;
  [key: string]: unknown;
}

export interface PosterSummaryResponse {
  "canvas_id": string;
  "created_at": string;
  "id": string;
  "layout_id": string;
  "name": string;
  "song_count": number;
  "theme_id": string;
  "updated_at": string;
  [key: string]: unknown;
}

export interface PracticeLogRequest {
  "event_id"?: string;
  "minutes"?: number;
  "note"?: string;
  "occurred_at"?: string;
  "self_rating"?: number;
  "song_id"?: string;
  "title_snapshot"?: string;
}

export interface PracticeLogResponse {
  "already_processed"?: boolean;
  "event_id": string;
  "minutes": number;
  "note"?: string;
  "ok"?: boolean;
  "self_rating": number;
  "title_snapshot"?: string;
  [key: string]: unknown;
}

export interface PracticeMonthSummaryResponse {
  "month": string;
  "rated_count": number;
  "rating_avg"?: number;
  "total_minutes": number;
  "total_sessions": number;
  "unique_songs": number;
  [key: string]: unknown;
}

export interface PracticeStatsResponse {
  "current_streak_days": number;
  "last_30_days": number;
  "longest_streak_days": number;
  "month_current_minutes"?: number;
  "month_current_sessions"?: number;
  "months"?: Array<Record<string, unknown>>;
  "songs_practiced": number;
  "top_practiced"?: Array<Record<string, unknown>>;
  "total_minutes": number;
  "total_sessions": number;
  [key: string]: unknown;
}

export interface PracticeStreakResponse {
  "current_streak": number;
  "first_date"?: string;
  "last_date"?: string;
  "longest_streak": number;
  "total_days": number;
  [key: string]: unknown;
}

export interface PresetDefaultResponse {
  "id": string;
  "ok"?: boolean;
  [key: string]: unknown;
}

export interface PresetDuplicateRequest {
  "name"?: string;
}

export interface PresetDuplicateResponse {
  "id": string;
  "name": string;
  "ok"?: boolean;
  [key: string]: unknown;
}

export interface PresetRequest {
  "canvas"?: Record<string, unknown>;
  "color_overrides"?: Record<string, unknown>;
  "created_at"?: string;
  "export"?: Record<string, unknown>;
  "id"?: string;
  "is_default"?: boolean;
  "layout_id"?: string;
  "name"?: string;
  "palette_id"?: string;
  "params"?: Record<string, unknown>;
  "schema_version"?: number;
  "skin_id"?: string;
  "song_query"?: SongQueryRequest;
  "updated_at"?: string;
}

export interface PresetResponse {
  "canvas"?: Record<string, unknown>;
  "color_overrides"?: Record<string, unknown>;
  "created_at"?: string;
  "export"?: Record<string, unknown>;
  "id"?: string;
  "is_default"?: boolean;
  "layout_id"?: string;
  "name"?: string;
  "palette_id"?: string;
  "params"?: Record<string, unknown>;
  "schema_version"?: number;
  "skin_id"?: string;
  "song_query"?: SongQueryRequest;
  "updated_at"?: string;
}

export interface PresetSaveResponse {
  "id": string;
  "ok"?: boolean;
  "updated_at": string;
  [key: string]: unknown;
}

export interface PresetSummaryResponse {
  "created_at": string;
  "id": string;
  "is_default": boolean;
  "layout_id": string;
  "name": string;
  "updated_at": string;
  [key: string]: unknown;
}

export interface RecentlySungItemResponse {
  "artist"?: string;
  "last_sung"?: string;
  "song_id": string;
  "times_sung"?: number;
  "title": string;
  [key: string]: unknown;
}

export interface RenderDocumentRequest {
  "canvas_id"?: string;
  "layout_id"?: string;
  "page"?: number;
  "parameters"?: Record<string, unknown>;
  "poster_id": string;
  "theme_id"?: string;
}

export interface RenderDocumentResponse {
  "canvas_id": string;
  "document"?: Record<string, unknown>;
  "document_id": string;
  "layout_id": string;
  "missing_song_ids"?: Array<string>;
  "page": number;
  "page_policy_mode"?: string;
  "pages_total": number;
  "poster_id": string;
  "song_count": number;
  "theme_id": string;
  [key: string]: unknown;
}

export interface RequestedSongItemResponse {
  "artist"?: string;
  "count"?: number;
  "last_requested"?: string;
  "song_id": string;
  "title": string;
  [key: string]: unknown;
}

export interface SettingsResponse {
  "appearanceMode"?: "system" | "light" | "dark";
  "applicationAccentId"?: "bambooMoon" | "rainSky" | "distantMountain" | "rouge" | "begonia" | "wisteria" | "amber" | "pineFlower";
  "backup_count": number;
  "default_canvas": string;
  "default_theme": string;
  "font_path": string;
  "output_dir": string;
  "render_threads": number;
  [key: string]: unknown;
}

export interface SettingsUpdateRequest {
  "appearanceMode"?: "system" | "light" | "dark" | null;
  "applicationAccentId"?: "bambooMoon" | "rainSky" | "distantMountain" | "rouge" | "begonia" | "wisteria" | "amber" | "pineFlower" | null;
  "backup_count"?: number | null;
  "default_canvas"?: string | null;
  "default_theme"?: string | null;
  "font_path"?: string | null;
  "output_dir"?: string | null;
  "render_threads"?: number | null;
}

export interface SettingsUpdateResponse {
  "ok"?: boolean;
  "settings": SettingsResponse;
  [key: string]: unknown;
}

export interface SongCreateRequest {
  "artists"?: Array<unknown> | null;
  "audio_duration_ms"?: unknown | null;
  "audio_instrumental_path"?: unknown | null;
  "audio_vocal_path"?: unknown | null;
  "capo"?: unknown | null;
  "capo_default"?: number | null;
  "capo_options"?: Array<number> | null;
  "composer"?: unknown | null;
  "difficulty"?: unknown | null;
  "key"?: unknown | null;
  "lyricist"?: unknown | null;
  "lyrics_lrc"?: unknown | null;
  "lyrics_plain"?: unknown | null;
  "notes"?: unknown | null;
  "pinyin"?: unknown | null;
  "section"?: unknown | null;
  "status"?: string | null;
  "tabs"?: unknown | null;
  "tags"?: Array<unknown> | null;
  "title"?: unknown | null;
}

export interface SongDeleteResponse {
  "active": number;
  "draft": number;
  "ok"?: boolean;
  "song_id": string;
  "title_snapshot": string;
  [key: string]: unknown;
}

export interface SongEditableFields {
  "artists"?: Array<unknown> | null;
  "audio_duration_ms"?: unknown | null;
  "audio_instrumental_path"?: unknown | null;
  "audio_vocal_path"?: unknown | null;
  "capo"?: unknown | null;
  "capo_default"?: number | null;
  "capo_options"?: Array<number> | null;
  "composer"?: unknown | null;
  "difficulty"?: unknown | null;
  "key"?: unknown | null;
  "lyricist"?: unknown | null;
  "lyrics_lrc"?: unknown | null;
  "lyrics_plain"?: unknown | null;
  "notes"?: unknown | null;
  "pinyin"?: unknown | null;
  "section"?: unknown | null;
  "tabs"?: unknown | null;
  "tags"?: Array<unknown> | null;
  "title"?: unknown | null;
}

export interface SongLegacyDeleteResponse {
  "active": number;
  "draft": number;
  "ok"?: boolean;
  "title": string;
  [key: string]: unknown;
}

export interface SongLegacyIdentityRequest {
  "title": string;
}

export interface SongLegacyStatusRequest {
  "status": string;
  "title": string;
}

export interface SongLegacyStatusResponse {
  "active": number;
  "draft": number;
  "ok"?: boolean;
  "status": string;
  "title": string;
  [key: string]: unknown;
}

export interface SongLegacyUpdateRequest {
  "fields": SongEditableFields;
  "title": string;
}

export interface SongMutationResponse {
  "active": number;
  "added"?: Array<string>;
  "draft": number;
  "ok"?: boolean;
  "song": SongResponse;
  [key: string]: unknown;
}

export interface SongQueryRequest {
  "classify"?: string;
  "custom_ids"?: Array<string>;
  "max_songs"?: number;
  "sort_by"?: string;
  "status"?: string;
  "unresolved"?: Array<string>;
}

export interface SongResponse {
  "added_at": string;
  "artists": Array<string>;
  "audio_duration_ms"?: number;
  "audio_instrumental_path"?: string;
  "audio_vocal_path"?: string;
  "capo": number | null;
  "capo_default"?: number;
  "capo_options"?: Array<number>;
  "composer": string;
  "deleted_at"?: string;
  "difficulty": string;
  "id": string;
  "key": string;
  "learned_at": string;
  "lyricist": string;
  "lyrics_lrc"?: string;
  "lyrics_plain"?: string;
  "notes": string;
  "pinyin": string;
  "section": number | null;
  "status": string;
  "tab_files": Array<string>;
  "tabs": string;
  "tags": Array<string>;
  "title": string;
  [key: string]: unknown;
}

export interface SongStatusRequest {
  "status": string;
}

export interface SongUpdateResponse {
  "ok"?: boolean;
  "song": SongResponse;
  [key: string]: unknown;
}

export interface SongsListResponse {
  "active": number;
  "draft": number;
  "songs": Array<SongResponse>;
  "total": number;
  [key: string]: unknown;
}

export interface SongsSummaryResponse {
  "by_len": Record<string, number>;
  "total": number;
  [key: string]: unknown;
}

export interface TopSongItemResponse {
  "artist"?: string;
  "count"?: number;
  "minutes"?: number;
  "song_id": string;
  "title": string;
  [key: string]: unknown;
}

export interface TopSongsResponse {
  "items"?: Array<TopSongItemResponse>;
  "metric": string;
  "note"?: string;
  [key: string]: unknown;
}

export interface ValidationError {
  "loc": Array<string | number>;
  "msg": string;
  "type": string;
  [key: string]: unknown;
}

// L2.2 批量按 ID 导出
export interface ExportByIdsFileResponse {
  "duration_ms": number | null;
  "filename": string;
  "path": string;
  "song_id": string;
  "title": string;
  [key: string]: unknown;
}

export interface ExportByIdsResponse {
  "files": Array<ExportByIdsFileResponse>;
  "ok"?: boolean;
  "total": number;
  "total_ms": number | null;
  [key: string]: unknown;
}

// L2.3 导入导出
export interface SongImportRequestBody {
  "mode": "merge" | "replace";
  "songs": Array<{
    "title": string;
    "artists"?: string[];
    "key"?: string;
    "capo"?: number | null;
    "difficulty"?: string;
    "tags"?: string[];
    "pinyin"?: string;
    "lyrics_lrc"?: string;
    "lyrics_plain"?: string;
    "notes"?: string;
    "section"?: number | null;
    "status"?: "active" | "draft";
  }>;
}

export interface SongImportResultResponse {
  "ok"?: boolean;
  "added": number;
  "skipped": number;
  "errors": string[];
  "active": number;
  "draft": number;
  [key: string]: unknown;
}

export interface SongExportResponse {
  "schema_version": number;
  "version": number;
  "songs": Array<Record<string, unknown>>;
  "exported_at": string;
  [key: string]: unknown;
}
