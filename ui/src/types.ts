/* ---- 共享类型（与后端 API 契约对应） ---- */
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
export interface Song {
  id: string;
  title: string;
  status: string;
  section: number | null;
  artists: string[];
  lyricist: string;
  composer: string;
  key: string;
  capo: number | null;
  difficulty: string;
  tabs: string;
  tags: string[];
  pinyin: string;
  added_at: string;
  notes: string;
  learned_at: string;
  tab_files: string[];
}
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
