// 此文件由 tools/generate_api_types.py 生成，请勿手工修改。
// OpenAPI JSON 是临时中间产物；本文件随源码提交。

export interface Body_api_tab_upload_api_songs__identity__tabs_post {
  "file": string;
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

export interface HTTPValidationError {
  "detail"?: Array<ValidationError>;
  [key: string]: unknown;
}

export interface OkResponse {
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

export interface SettingsResponse {
  "backup_count": number;
  "default_canvas": string;
  "default_theme": string;
  "font_path": string;
  "output_dir": string;
  "render_threads": number;
  [key: string]: unknown;
}

export interface SettingsUpdateRequest {
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
  "capo"?: unknown | null;
  "composer"?: unknown | null;
  "difficulty"?: unknown | null;
  "key"?: unknown | null;
  "lyricist"?: unknown | null;
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
  "capo"?: unknown | null;
  "composer"?: unknown | null;
  "difficulty"?: unknown | null;
  "key"?: unknown | null;
  "lyricist"?: unknown | null;
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
  "capo": number | null;
  "composer": string;
  "difficulty": string;
  "id": string;
  "key": string;
  "learned_at": string;
  "lyricist": string;
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

export interface ValidationError {
  "loc": Array<string | number>;
  "msg": string;
  "type": string;
  [key: string]: unknown;
}
