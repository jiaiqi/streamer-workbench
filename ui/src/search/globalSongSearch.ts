/// M1.1 蓝图 v0.1 全局找歌 — 多字段加权排序
///
/// 设计：
/// - 搜索字段：歌名 / 歌手 / 拼音首字母 / 歌词片段 / 标签 / 调式
/// - 排序权重（蓝图 §3.2）：
///   1. 名称完全匹配 = 100
///   2. 名称前缀匹配 = 80
///   3. 歌手匹配 = 60
///   4. 拼音匹配 = 50
///   5. 歌词片段匹配 = 40
///   6. 标签匹配 = 30
///   7. 调式匹配 = 20
///   8. 名称包含 = 10
/// 排序：分数 > 0，按分数降序；相同分数按 title 升序。
/// 返回前 N 条（默认 20）。
import type { Song } from "../types";

export interface SongSearchOptions {
  /** 返回条数上限（默认 20） */
  limit?: number;
  /** 仅返回 active 状态歌曲（默认 true） */
  activeOnly?: boolean;
}

interface ScoredSong {
  song: Song;
  score: number;
  matchedField: "title" | "title_prefix" | "artist" | "pinyin" | "lyrics" | "tag" | "key" | "title_contains";
}

function normalize(s: string): string {
  return s.toLowerCase().trim();
}

function contains(haystack: string, needle: string): boolean {
  return normalize(haystack).includes(normalize(needle));
}

function scoreSong(song: Song, query: string): ScoredSong | null {
  const q = query.trim();
  if (!q) return null;
  const qLower = q.toLowerCase();

  // 1. 歌名完全匹配
  if (normalize(song.title) === qLower) {
    return { song, score: 100, matchedField: "title" };
  }
  // 2. 歌名前缀匹配
  if (normalize(song.title).startsWith(qLower)) {
    return { song, score: 80, matchedField: "title_prefix" };
  }
  // 3. 歌手匹配（任一歌手匹配）
  if (song.artists.some(a => contains(a, q))) {
    return { song, score: 60, matchedField: "artist" };
  }
  // 4. 拼音首字母匹配（已存的 pinyin 字段就是首字母）
  if (song.pinyin && contains(song.pinyin, q)) {
    return { song, score: 50, matchedField: "pinyin" };
  }
  // 5. 歌词片段匹配（LRC + plain 文本）
  if (song.lyrics_lrc && contains(song.lyrics_lrc, q)) {
    return { song, score: 40, matchedField: "lyrics" };
  }
  if (song.lyrics_plain && contains(song.lyrics_plain, q)) {
    return { song, score: 40, matchedField: "lyrics" };
  }
  // 6. 标签匹配
  if (song.tags && song.tags.some(t => contains(t, q))) {
    return { song, score: 30, matchedField: "tag" };
  }
  // 7. 调式匹配（Key 字段：原调 C/D/E + 小调 Am/Em）
  if (song.key && contains(song.key, q)) {
    return { song, score: 20, matchedField: "key" };
  }
  // 8. 名称包含（兜底）
  if (contains(song.title, q)) {
    return { song, score: 10, matchedField: "title_contains" };
  }
  return null;
}

export function searchSongs(
  query: string,
  songs: Song[],
  options: SongSearchOptions = {},
): Song[] {
  const { limit = 20, activeOnly = true } = options;
  if (!query.trim()) return [];
  const pool = activeOnly ? songs.filter(s => s.status === "active") : songs;
  const scored: ScoredSong[] = [];
  for (const song of pool) {
    const result = scoreSong(song, query);
    if (result) scored.push(result);
  }
  // 排序：分数降序 → title 升序
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.song.title.localeCompare(b.song.title, "zh-CN");
  });
  return scored.slice(0, limit).map(s => s.song);
}
