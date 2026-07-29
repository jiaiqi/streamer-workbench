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
export interface ParamSpec {
  key: string;
  label: string;
  kind: string;            // "int" | "color" | "bool" | "choice"
  default: number;
  min: number | null;
  max: number | null;
  choices: string[] | null;
}
export interface Settings {
  output_dir: string;
  default_canvas: string;
  default_theme: string;
  font_path: string;
  backup_count: number;
  render_threads: number;
}

export const CANVAS_OPTIONS = ["标准 9:16", "抖音全屏 9:20"] as const;
