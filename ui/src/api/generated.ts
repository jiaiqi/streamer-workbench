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

export interface ValidationError {
  "loc": Array<string | number>;
  "msg": string;
  "type": string;
  [key: string]: unknown;
}
