/// M1.1 globalSongSearch 测试
import { describe, expect, it } from "vitest";
import { searchSongs } from "./globalSongSearch";
import type { Song } from "../types";

const SAMPLE_SONGS: Song[] = [
  {
    id: "song_1",
    title: "江南",
    status: "active",
    section: 3,
    artists: ["林俊杰"],
    lyricist: "", composer: "",
    key: "C", capo: 0,
    difficulty: "", tabs: "", tags: [],
    pinyin: "jiangnan", notes: "", added_at: "", learned_at: "",
    tab_files: [], lyrics_lrc: "", lyrics_plain: "",
    audio_vocal_path: "", audio_instrumental_path: "",
    audio_duration_ms: 0,
  },
  {
    id: "song_2",
    title: "十年",
    status: "active",
    section: 2,
    artists: ["陈奕迅"],
    lyricist: "", composer: "",
    key: "G", capo: 0,
    difficulty: "", tabs: "", tags: ["经典"],
    pinyin: "shinian", notes: "", added_at: "", learned_at: "",
    tab_files: [],
    lyrics_lrc: "[00:00.00]十年之前我不认识你",
    lyrics_plain: "",
    audio_vocal_path: "", audio_instrumental_path: "",
    audio_duration_ms: 0,
  },
  {
    id: "song_3",
    title: "江南雨",
    status: "active",
    section: 3,
    artists: ["小娟"],
    lyricist: "", composer: "",
    key: "D", capo: 0,
    difficulty: "", tabs: "", tags: [],
    pinyin: "jiangnanyu", notes: "", added_at: "", learned_at: "",
    tab_files: [],
    lyrics_lrc: "[00:00.00]江南雨落",
    lyrics_plain: "",
    audio_vocal_path: "", audio_instrumental_path: "",
    audio_duration_ms: 0,
  },
  {
    id: "song_4",
    title: "青花瓷",
    status: "draft",
    section: 3,
    artists: ["周杰伦"],
    lyricist: "", composer: "",
    key: "A", capo: 0,
    difficulty: "", tabs: "", tags: [],
    pinyin: "qinghuaci", notes: "", added_at: "", learned_at: "",
    tab_files: [],
    lyrics_lrc: "[00:00.00]素胚勾勒出青花",
    lyrics_plain: "",
    audio_vocal_path: "", audio_instrumental_path: "",
    audio_duration_ms: 0,
  },
  {
    id: "song_5",
    title: "玫瑰",
    status: "active",
    section: 2,
    artists: ["贰佰"],
    lyricist: "", composer: "",
    key: "B", capo: 0,  // 唯 B 调
    difficulty: "", tabs: "", tags: [],
    pinyin: "mg", notes: "", added_at: "", learned_at: "",
    tab_files: [],
    lyrics_lrc: "[00:00.00]玫瑰的名字",
    lyrics_plain: "",
    audio_vocal_path: "", audio_instrumental_path: "",
    audio_duration_ms: 0,
  },
];

describe("searchSongs - 多字段加权", () => {
  it("空查询返回空", () => {
    expect(searchSongs("", SAMPLE_SONGS)).toEqual([]);
    expect(searchSongs("   ", SAMPLE_SONGS)).toEqual([]);
  });

  it("完全匹配 title 得 100 分（最高）", () => {
    const r = searchSongs("江南", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_1");
    expect(r.length).toBe(2);  // "江南" + "江南雨"
  });

  it("歌手匹配得 60 分", () => {
    const r = searchSongs("林俊杰", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_1");
  });

  it("拼音首字母匹配得 50 分", () => {
    const r = searchSongs("shinian", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_2");
  });

  it("歌词片段匹配得 40 分（模糊子串）", () => {
    const r = searchSongs("十年之前", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_2");
  });

  it("标签匹配得 30 分", () => {
    const r = searchSongs("经典", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_2");
  });

  it("调式匹配得 20 分", () => {
    // song_5 唯一 key="B" + 拼音 "mg" 不含 "B"（避开拼音匹配干扰）
    const r = searchSongs("B", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_5");
  });

  it("activeOnly 默认过滤 draft 歌曲", () => {
    const r = searchSongs("青花", SAMPLE_SONGS);
    expect(r).toEqual([]);  // 青花瓷是 draft
  });

  it("activeOnly=false 包含 draft", () => {
    const r = searchSongs("青花", SAMPLE_SONGS, { activeOnly: false });
    expect(r[0].id).toBe("song_4");
  });

  it("按分数降序排序（不区分大小写）", () => {
    const r = searchSongs("江南", SAMPLE_SONGS);
    // 第一个应为完全匹配（100 分）
    expect(r[0].id).toBe("song_1");
    // 第二个应为名称包含（10 分）
    expect(r[1].id).toBe("song_3");
  });

  it("limit 限制返回条数", () => {
    const r = searchSongs("江南", SAMPLE_SONGS, { limit: 1 });
    expect(r.length).toBe(1);
  });

  it("完全不匹配返回空", () => {
    const r = searchSongs("完全不存在的关键词xyz", SAMPLE_SONGS);
    expect(r).toEqual([]);
  });

  it("中文标签 + 英文小写不敏感", () => {
    const r = searchSongs("经典", SAMPLE_SONGS);
    expect(r[0].id).toBe("song_2");
  });
});
