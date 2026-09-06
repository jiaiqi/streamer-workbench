/// P1-A1.2: 就绪度 4 徽章共享 lib。
///
/// 设计动机（design/prototypes/2026-09-06-功能与UIUX优化分析.md §1 判断 3）：
///   原 ReadinessCheck 逻辑深嵌在 TonightWorkbench 组件内（925 行），
///   LibraryView / 学歌 / 弹唱等视图看不到"今晚能弹唱吗"。
///   抽离纯函数 + 共享类型 → 任何视图可独立计算 + 渲染 4 枚徽章。
///
/// 范围（v0.1，最小切片）：
/// - 纯函数 evaluateReadiness：接受 SongForReadiness 子集字段 → 返回缺失字段名列表
/// - READINESS_FIELDS：4 枚徽章的展示顺序 + 中文标签
/// - 类型 ReadinessField：4 字段的字面量联合
/// - 类型 ReadinessReport：D 区"就绪 N/M"聚合报告
/// - 类型 SongForReadiness：9 字段最小窄类型（避免 import 整个 Song 模型）
///
/// 不在本次范围（避免 scope creep）：
/// - 抽出 ReadinessCheck 渲染层（那是另一条 commit，触及 TonightWorkbench 测试）
/// - LibraryView 接入（再另一条 commit）
/// - 任何网络请求逻辑（纯函数 + 数据）
///
/// 不触碰 core/ / server/ 任何 Python 边界。

/** 4 枚徽章的字段名（保持与 evaluateReadiness 输出顺序一致） */
export const READINESS_FIELDS = ["tabs", "lyrics", "audio", "key"] as const;
export type ReadinessField = (typeof READINESS_FIELDS)[number];

/** 4 枚徽章的中文标签（与原 TonightWorkbench 行为完全一致） */
export const READINESS_FIELDS_LOOKUP: Record<ReadinessField, string> = {
  tabs: "曲谱",
  lyrics: "歌词",
  audio: "音频",
  key: "Key",
};

/**
 * 9 字段最小窄类型 — 任何视图（TonightWorkbench / LibraryView / 学歌 / 弹唱）
 * 只要能提供这 9 字段就能计算就绪度。避免强制 import 整个 Song 模型。
 */
export interface SongForReadiness {
  id: string;
  title: string;
  /** song tabs field — chart / chordpro 文本 */
  tabs: string;
  /** 纯文本歌词（无时间戳） */
  lyrics_plain: string;
  /** LRC 时间戳歌词（与 lyrics_plain 二选一即可） */
  lyrics_lrc: string;
  /** 人声音频路径（null = 未上传） */
  audio_vocal_path: string | null;
  /** 调式主音（C / D / F# / ...），空 = 未设 */
  key: string;
}

/** 缺失字段名列表（按 READINESS_FIELDS 顺序；空数组 = 4 项全齐） */
export type ReadinessMissing = ReadinessField[];

/** 纯函数：评估一首歌的就绪度，返回缺失字段列表。 */
export function evaluateReadiness(song: SongForReadiness): ReadinessMissing {
  const missing: ReadinessMissing = [];
  if (!song.tabs || song.tabs.trim() === "") missing.push("tabs");
  if (
    (!song.lyrics_plain || song.lyrics_plain.trim() === "") &&
    (!song.lyrics_lrc || song.lyrics_lrc.trim() === "")
  ) {
    missing.push("lyrics");
  }
  if (!song.audio_vocal_path) missing.push("audio");
  if (!song.key || song.key.trim() === "") missing.push("key");
  return missing;
}

/** 便捷：4 项是否全齐 */
export function isFullyReady(song: SongForReadiness): boolean {
  return evaluateReadiness(song).length === 0;
}

/** 4 枚徽章的展示形态（用于 ReadinessBadge 组件） */
export interface ReadinessChipSpec {
  field: ReadinessField;
  label: string;
  /** true = 已就绪（绿色），false = 缺失（灰/警告色） */
  ready: boolean;
}

/** 把一首歌的就绪度摊平为 4 枚徽章的展示数组（顺序固定：tabs → lyrics → audio → key） */
export function buildReadinessChips(song: SongForReadiness): ReadinessChipSpec[] {
  const missing = evaluateReadiness(song);
  const missingSet = new Set(missing);
  return READINESS_FIELDS.map((field) => ({
    field,
    label: READINESS_FIELDS_LOOKUP[field],
    ready: !missingSet.has(field),
  }));
}

/** 聚合报告（D 区"就绪 N/M"） */
export interface ReadinessReport {
  ready: number;
  total: number;
  missing: Array<{ songId: string; title: string; missing: ReadinessMissing }>;
}

/** 纯函数：对一组歌曲聚合就绪度报告。 */
export function aggregateReadiness(
  songs: SongForReadiness[],
): ReadinessReport {
  let ready = 0;
  const missing: ReadinessReport["missing"] = [];
  for (const s of songs) {
    const m = evaluateReadiness(s);
    if (m.length === 0) ready += 1;
    else missing.push({ songId: s.id, title: s.title, missing: m });
  }
  return { ready, total: songs.length, missing };
}
