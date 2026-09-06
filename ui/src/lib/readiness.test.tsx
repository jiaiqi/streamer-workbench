/// P1-A1.2: 就绪度共享 lib 单测。
///
/// 覆盖（9 个 spec）：
/// 1. evaluateReadiness 全部 4 项都齐 → 空数组
/// 2. evaluateReadiness 全空 → 4 项缺失（顺序固定）
/// 3. evaluateReadiness 半空（仅 tabs/lyrics）→ 2 项缺失
/// 4. evaluateReadiness lyrics_plain 与 lyrics_lrc 二选一即可
/// 5. evaluateReadiness 字段顺序固定（与原 TonightWorkbench 行为一致）
/// 6. isFullyReady true/false 分支
/// 7. buildReadinessChips 4 枚徽章 + 顺序 + ready 标志
/// 8. aggregateReadiness 多首歌聚合（含 0 首歌边界）
/// 9. READINESS_FIELDS 长度恒为 4（防止未来误删字段）
import { describe, expect, it } from "vitest";
import {
  evaluateReadiness,
  isFullyReady,
  buildReadinessChips,
  aggregateReadiness,
  READINESS_FIELDS,
  READINESS_FIELDS_LOOKUP,
  type SongForReadiness,
} from "./readiness";

const fullSong: SongForReadiness = {
  id: "song_full",
  title: "全部就绪",
  tabs: "[Verse]\nC G",
  lyrics_plain: "副歌歌词",
  lyrics_lrc: "[00:01.00]副歌歌词",
  audio_vocal_path: "/data/audio/song_full/vocal.m4a",
  key: "C",
};

const emptySong: SongForReadiness = {
  id: "song_empty",
  title: "全部缺失",
  tabs: "",
  lyrics_plain: "",
  lyrics_lrc: "",
  audio_vocal_path: null,
  key: "",
};

describe("evaluateReadiness", () => {
  it("全部 4 项都齐 → 缺失列表为空", () => {
    expect(evaluateReadiness(fullSong)).toEqual([]);
  });

  it("全空 → 4 项缺失（顺序：tabs lyrics audio key）", () => {
    expect(evaluateReadiness(emptySong)).toEqual(["tabs", "lyrics", "audio", "key"]);
  });

  it("半空（仅 tabs/lyrics 缺失）→ 2 项缺失", () => {
    const song: SongForReadiness = {
      ...fullSong,
      tabs: "",
      lyrics_plain: "",
      lyrics_lrc: "",  // 二者都空 → lyrics 算缺失
    };
    expect(evaluateReadiness(song)).toEqual(["tabs", "lyrics"]);
  });

  it("lyrics_plain 与 lyrics_lrc 二选一即可（两者都空才算缺失）", () => {
    const songLrcOnly: SongForReadiness = {
      ...fullSong,
      lyrics_plain: "",
      lyrics_lrc: "[00:01.00]LRC 歌词",
    };
    expect(evaluateReadiness(songLrcOnly)).not.toContain("lyrics");
    const songPlainOnly: SongForReadiness = {
      ...fullSong,
      lyrics_plain: "纯文本歌词",
      lyrics_lrc: "",
    };
    expect(evaluateReadiness(songPlainOnly)).not.toContain("lyrics");
  });

  it("字段顺序固定（与原 TonightWorkbench 行为一致）", () => {
    const song: SongForReadiness = {
      ...fullSong,
      key: "",          // key 缺失
      audio_vocal_path: null,  // audio 缺失
      tabs: "",         // tabs 缺失
      lyrics_plain: "", lyrics_lrc: "",  // lyrics 缺失
    };
    // 即使后端数据 key/audio 先缺失，evaluateReadiness 也按 tabs→lyrics→audio→key 顺序
    expect(evaluateReadiness(song)).toEqual(["tabs", "lyrics", "audio", "key"]);
  });
});

describe("isFullyReady", () => {
  it("全齐 → true", () => {
    expect(isFullyReady(fullSong)).toBe(true);
  });
  it("有缺失 → false", () => {
    expect(isFullyReady(emptySong)).toBe(false);
    expect(isFullyReady({ ...fullSong, key: "" })).toBe(false);
  });
});

describe("buildReadinessChips", () => {
  it("4 枚徽章，顺序固定，ready 标志正确", () => {
    const chips = buildReadinessChips({
      ...fullSong,
      tabs: "",            // 缺曲谱
      audio_vocal_path: null,  // 缺音频
    });
    expect(chips).toHaveLength(4);
    expect(chips.map(c => c.field)).toEqual(["tabs", "lyrics", "audio", "key"]);
    expect(chips.map(c => c.label)).toEqual(["曲谱", "歌词", "音频", "Key"]);
    // tabs 和 audio 缺失
    expect(chips.find(c => c.field === "tabs")?.ready).toBe(false);
    expect(chips.find(c => c.field === "lyrics")?.ready).toBe(true);
    expect(chips.find(c => c.field === "audio")?.ready).toBe(false);
    expect(chips.find(c => c.field === "key")?.ready).toBe(true);
  });
});

describe("aggregateReadiness", () => {
  it("空数组 → ready=0, total=0, missing=[]", () => {
    expect(aggregateReadiness([])).toEqual({ ready: 0, total: 0, missing: [] });
  });
  it("混合 2 首歌（1 齐 1 不齐）", () => {
    const report = aggregateReadiness([fullSong, emptySong]);
    expect(report.ready).toBe(1);
    expect(report.total).toBe(2);
    expect(report.missing).toHaveLength(1);
    expect(report.missing[0].songId).toBe("song_empty");
    expect(report.missing[0].missing).toEqual(["tabs", "lyrics", "audio", "key"]);
  });
});

describe("READINESS_FIELDS 常量", () => {
  it("长度恒为 4（防止未来误删字段）", () => {
    expect(READINESS_FIELDS).toHaveLength(4);
  });
  it("LOOKUP 覆盖全部 4 字段（防止新字段忘记加中文标签）", () => {
    for (const f of READINESS_FIELDS) {
      expect(READINESS_FIELDS_LOOKUP[f]).toBeTruthy();
    }
  });
});
