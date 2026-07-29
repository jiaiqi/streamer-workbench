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

export interface HTTPValidationError {
  "detail"?: Array<ValidationError>;
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
