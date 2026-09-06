/* ---- 测试共享工厂：与后端 OpenAPI 契约对齐的歌曲样例 ---- */
import type { Song } from "./types";

/**
 * SongResponse 必填字段的完整基线样例。
 * tsc -b 会把 *.test.tsx 一并类型检查（tsconfig.app.json 不再 exclude），
 * 测试样例必须过 Song 类型，避免契约漂移。
 */
const BASE_SONG: Song = {
  id: "song_test_aaaaaaaaaaaaa",
  title: "江南",
  artists: ["林俊杰"],
  composer: "",
  lyricist: "",
  status: "active",
  added_at: "2026-08-30T10:00:00",
  learned_at: "",
  key: "C",
  capo: 0,
  capo_default: undefined,
  capo_options: undefined,
  difficulty: "中等",
  section: null,
  tags: ["流行"],
  pinyin: "jiang nan",
  tabs: "",
  tab_files: [],
  notes: "",
  lyrics_lrc: "",
  lyrics_plain: "",
  audio_vocal_path: "",
  audio_instrumental_path: "",
  audio_duration_ms: 0,
};

/** 生成一个类型完整的 Song 样例；overrides 覆盖任意字段。 */
export function makeSong(overrides: Partial<Song> = {}): Song {
  return { ...BASE_SONG, ...overrides };
}
