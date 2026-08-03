/// M1.1 蓝图 v0.1 全局找歌 — 多字段加权排序 + M2.5 events 热度反哺
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
/// - M2.5 反哺：基础分 + events 热度加成（log2 压缩，上限 +50，避免热门歌曲垄断）
/// 排序：分数 > 0，按分数降序；相同分数按 title 升序。
/// 返回前 N 条（默认 20）。
import type { Song } from "../types";

export interface SongSearchOptions {
  /** 返回条数上限（默认 20） */
  limit?: number;
  /** 仅返回 active 状态歌曲（默认 true） */
  activeOnly?: boolean;
  /** M2.5: events 热度图（song_id → queue_added 次数）加分用 */
  eventsHeat?: Map<string, number>;
}

interface ScoredSong {
  song: Song;
  score: number;
  matchedField: "title" | "title_prefix" | "artist" | "pinyin" | "lyrics" | "tag" | "key" | "title_contains";
}

/** M2.5: events 热度加成（log2 压缩） — count=5 → +13, count=20 → +22, count=100 → +33, count=1000 → +49 */
export function heatBonus(count: number | undefined): number {
  if (!count || count <= 0) return 0;
  return Math.min(50, Math.floor(Math.log2(count + 1) * 5));
}

/** M2.5: 从 events.jsonl 拉到的 events 数组构建热度图（按 song_id 累加 queue_added 次数） */
export function buildEventsHeat(events: Array<{ song_id?: string | null }> | null | undefined): Map<string, number> {
  const out = new Map<string, number>();
  if (!events) return out;
  for (const ev of events) {
    const id = ev?.song_id;
    if (!id) continue;
    out.set(id, (out.get(id) ?? 0) + 1);
  }
  return out;
}

function normalize(s: string): string {
  return s.toLowerCase().trim();
}

function contains(haystack: string, needle: string): boolean {
  return normalize(haystack).includes(normalize(needle));
}

function scoreSong(song: Song, query: string, eventsHeat?: Map<string, number>): ScoredSong | null {
  const q = query.trim();
  if (!q) return null;
  const qLower = q.toLowerCase();
  const bonus = heatBonus(eventsHeat?.get(song.id));

  // 1. 歌名完全匹配
  if (normalize(song.title) === qLower) {
    return { song, score: 100 + bonus, matchedField: "title" };
  }
  // 2. 歌名前缀匹配
  if (normalize(song.title).startsWith(qLower)) {
    return { song, score: 80 + bonus, matchedField: "title_prefix" };
  }
  // 3. 歌手匹配（任一歌手匹配）
  if (song.artists.some(a => contains(a, q))) {
    return { song, score: 60 + bonus, matchedField: "artist" };
  }
  // 4. 拼音首字母匹配（已存的 pinyin 字段就是首字母）
  if (song.pinyin && contains(song.pinyin, q)) {
    return { song, score: 50 + bonus, matchedField: "pinyin" };
  }
  // 5. 歌词片段匹配（LRC + plain 文本）
  if (song.lyrics_lrc && contains(song.lyrics_lrc, q)) {
    return { song, score: 40 + bonus, matchedField: "lyrics" };
  }
  if (song.lyrics_plain && contains(song.lyrics_plain, q)) {
    return { song, score: 40 + bonus, matchedField: "lyrics" };
  }
  // 6. 标签匹配
  if (song.tags && song.tags.some(t => contains(t, q))) {
    return { song, score: 30 + bonus, matchedField: "tag" };
  }
  // 7. 调式匹配（Key 字段：原调 C/D/E + 小调 Am/Em）
  if (song.key && contains(song.key, q)) {
    return { song, score: 20 + bonus, matchedField: "key" };
  }
  // 8. 名称包含（兜底）
  if (contains(song.title, q)) {
    return { song, score: 10 + bonus, matchedField: "title_contains" };
  }
  return null;
}

export function searchSongs(
  query: string,
  songs: Song[],
  options: SongSearchOptions = {},
): Song[] {
  const { limit = 20, activeOnly = true, eventsHeat } = options;
  if (!query.trim()) return [];
  const pool = activeOnly ? songs.filter(s => s.status === "active") : songs;
  const scored: ScoredSong[] = [];
  for (const song of pool) {
    const result = scoreSong(song, query, eventsHeat);
    if (result) scored.push(result);
  }
  // 排序：分数降序 → title 升序
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.song.title.localeCompare(b.song.title, "zh-CN");
  });
  return scored.slice(0, limit).map(s => s.song);
}
