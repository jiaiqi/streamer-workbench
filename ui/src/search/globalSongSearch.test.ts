/// M1.1 globalSongSearch 测试
import { describe, expect, it } from "vitest";
import { buildEventsHeat, heatBonus, searchSongs } from "./globalSongSearch";
import type { Song } from "../types";
import { makeSong } from "../test-fixtures";

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

describe("searchSongs - M2.5 eventsHeat 加成", () => {
  it("eventsHeat 高热度歌曲排前：完全匹配 + bonus(count=3)=10 < 兜底 + bonus(count=20)=22", () => {
    const songs = [
      mkSong({ id: "s_a", title: "晴天" }),         // 完全匹配 100 + bonus=10 = 110
      mkSong({ id: "s_b", title: "晴天后半段" }),   // 名称包含 10 + bonus=22 = 32
    ];
    const heat = new Map([["s_a", 3], ["s_b", 20]]);
    const r = searchSongs("晴天", songs, { eventsHeat: heat });
    expect(r[0].id).toBe("s_a");  // 110
    expect(r[1].id).toBe("s_b");  // 32
  });

  it("eventsHeat 反转排序：低基础分 + 高热度胜过高基础分 + 低热度", () => {
    // s_hot 走 title_contains(10) + bonus(100)=33 = 43
    // s_cold 走 lyrics(40) + bonus(0)=0 = 40
    // bonus 让低基础分反超 3 分
    const songs = [
      mkSong({ id: "s_hot", title: "不插电夜曲集" }),
      mkSong({ id: "s_cold", title: "十年", lyrics_lrc: "夜晚唱着夜曲" }),
    ];
    const heat = new Map([["s_hot", 100]]);
    const r = searchSongs("夜曲", songs, { eventsHeat: heat });
    expect(r[0].id).toBe("s_hot");   // 43（低基础分 10 + 热度 33 反超）
    expect(r[1].id).toBe("s_cold");  // 40（高基础分 40 无热度加成）
  });

  it("eventsHeat Map 为空 → 0 bonus，排序按基础分", () => {
    const songs = [
      mkSong({ id: "s_a", title: "晴天" }),
      mkSong({ id: "s_b", title: "晴天后半段" }),
    ];
    const r = searchSongs("晴天", songs, { eventsHeat: new Map() });
    expect(r[0].id).toBe("s_a");   // 100
    expect(r[1].id).toBe("s_b");   // 10
  });

  it("不传 eventsHeat → 不抛错，行为同 M1.1", () => {
    const songs = [mkSong({ id: "s_a", title: "晴天" })];
    const r = searchSongs("晴天", songs);
    expect(r[0].id).toBe("s_a");
  });

  it("count 极大时 bonus 上限 50（避免热门歌曲垄断）", () => {
    const songs = [
      mkSong({ id: "s_cold", title: "晴天" }),            // 100 + 0
      mkSong({ id: "s_hot", title: "晴天" }),             // 100 + 50 = 150
      mkSong({ id: "s_prefix", title: "晴天后半段" }),    // 80 + 50 = 130
    ];
    const heat = new Map([["s_hot", 10000], ["s_prefix", 10000]]);
    const r = searchSongs("晴天", songs, { eventsHeat: heat });
    expect(r[0].id).toBe("s_hot");
    expect(r[1].id).toBe("s_prefix");
    expect(r[2].id).toBe("s_cold");
  });
});

// ---- M2.5 测试辅助：mkSong（复用共享工厂保证 Song 契约字段完整）----
const mkSong = makeSong;

describe("buildEventsHeat + heatBonus (M2.5 反哺 App)", () => {
  it("heatBonus: log2 压缩加成", () => {
    expect(heatBonus(undefined)).toBe(0);
    expect(heatBonus(0)).toBe(0);
    expect(heatBonus(1)).toBe(5);   // log2(2)*5 = 5
    expect(heatBonus(3)).toBe(10);  // log2(4)*5 = 10
    expect(heatBonus(7)).toBe(15);  // log2(8)*5 = 15
    expect(heatBonus(15)).toBe(20); // log2(16)*5 = 20
    expect(heatBonus(100)).toBe(33);
    expect(heatBonus(10000)).toBe(50); // 上限
  });

  it("buildEventsHeat: 累加 song_id 出现次数", () => {
    const heat = buildEventsHeat([
      { song_id: "s_a" },
      { song_id: "s_b" },
      { song_id: "s_a" },
      { song_id: "s_a" },
    ]);
    expect(heat.get("s_a")).toBe(3);
    expect(heat.get("s_b")).toBe(1);
  });

  it("buildEventsHeat: 跳过 song_id 缺失的事件", () => {
    const heat = buildEventsHeat([
      { song_id: null },
      { song_id: "" },
      { song_id: "s_a" },
      {},
    ]);
    expect(heat.size).toBe(1);
    expect(heat.get("s_a")).toBe(1);
  });

  it("buildEventsHeat: 入参 null/undefined/[] 返回空 Map", () => {
    expect(buildEventsHeat(null).size).toBe(0);
    expect(buildEventsHeat(undefined).size).toBe(0);
    expect(buildEventsHeat([]).size).toBe(0);
  });

  it("searchSongs 透传 buildEventsHeat 出的 Map（端到端反哺链路）", () => {
    const heat = buildEventsHeat([
      { song_id: "s_hot" }, { song_id: "s_hot" }, { song_id: "s_hot" },
    ]);
    const songs = [
      mkSong({ id: "s_hot", title: "不插电夜曲集" }),
      mkSong({ id: "s_cold", title: "十年", lyrics_lrc: "夜晚唱着夜曲" }),
    ];
    const r = searchSongs("夜曲", songs, { eventsHeat: heat });
    // s_hot: title_contains 10 + bonus(3)=10 = 20
    // s_cold: lyrics 40 + 0 = 40
    // s_cold 仍排前（热度不够反超）
    expect(r[0].id).toBe("s_cold");
    expect(r[1].id).toBe("s_hot");
  });
});
