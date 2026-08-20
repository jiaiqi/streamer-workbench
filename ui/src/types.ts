/* ---- 共享类型（与后端 API 契约对应） ---- */
import type { SongResponse } from "./api/generated";

export interface Theme {
  name: string;
  prefix: string;
  watermark_fix: boolean;
  backgrounds: Record<string, string>;
  notes: string;
}
export interface Layout {
  id: string;
  name: string;
  pages: number;
  supports_avoidance: boolean;
}
/**
 * 业务代码统一使用 Song 类型。
 * 字段从后端 OpenAPI 生成的 SongResponse 派生（types.ts:1 之后禁止手抄字段），
 * 既保证 lyric/audio 字段同步，也避免手工类型与 OpenAPI 漂移。
 */
export type Song = SongResponse;

export interface SongsData {
  total: number;
  active: number;
  draft: number;
  songs: Song[];
}
export type ParamSpecKind =
  | "int" | "float" | "bool" | "select" | "section_map" | "group_order";

export interface ColumnTemplate {
  key: string;             // "balanced" | "dense" | "spacious" | "magazine" | "custom"
  label: string;           // 显示名
  description: string;
  values: Record<string, number>;  // 8 个字数分组 → 栏数
}

export interface ParamSpec {
  key: string;
  label: string;
  kind: ParamSpecKind;
  default: unknown;          // kind 决定形状: int/number/boolean/string | section_map→Record<string, number> | group_order→string[]
  min?: number | null;
  max?: number | null;
  step?: number | null;
  choices?: Array<string | number> | null;
  group?: string;            // "布局"/"样式"/"画布"/"分组"
  help?: string;
  section_axis?: string | null;   // kind=section_map 时绑定
  unit?: string;             // "px"/"pt" 等
}
export interface Settings {
  output_dir: string;
  default_canvas: string;
  default_theme: string;
  font_path: string;
  backup_count: number;
  render_threads: number;
  appearanceMode?: AppearanceMode;
  applicationAccentId?: ApplicationAccentId;
}

export type AppearanceMode = "system" | "light" | "dark";
export type ApplicationAccentId = "bambooMoon" | "rainSky" | "distantMountain" | "rouge" | "begonia" | "wisteria" | "amber" | "pineFlower";

export interface AppearanceSettings {
  appearanceMode: AppearanceMode;
  applicationAccentId: ApplicationAccentId;
}

export const CANVAS_OPTIONS = ["标准 9:16", "抖音全屏 9:20"] as const;
