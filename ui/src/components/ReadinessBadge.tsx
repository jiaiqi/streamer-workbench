/// P1-A1.2: ReadinessBadge — 就绪度 4 徽章渲染组件。
///
/// 设计动机（design/prototypes/2026-09-06-功能与UIUX优化分析.md §1 判断 3）：
///   LibraryView / 学歌 / 弹唱等视图看不到"今晚能弹唱吗"。
///   主播打开 LibraryView 时希望"一瞥即知"每首歌的就绪度。
///
/// 行为：
///   - 接受 4 字段（来自 lib/readiness.ts SongForReadiness）
///   - 内部走 evaluateReadiness → 渲染 4 枚徽章（tabs / lyrics / audio / key）
///   - 已就绪 = 绿勾 / 缺失 = 灰叉
///   - WCAG AA：与 R5c 颜色 token 一致（已就绪走 emerald，缺失走 muted-foreground）
///
/// Props：
///   - song: 接受整个 Song 对象（generated.ts 的 SongResponse），内部做 undefined → 空串防御
///   - size: 'xs' | 'sm'（默认 'xs'，行内 12px 适配 LibraryView 元数据行）
///   - dark: 暗色模式
///   - className: 容器外层 class（用于布局微调）
///
/// 不在本组件范围：
///   - 拉取后端数据（pure presentation）
///   - 点击徽章触发"补什么"动作（v0.2 计划）
import { evaluateReadiness, READINESS_FIELDS, READINESS_FIELDS_LOOKUP, type ReadinessField } from "../lib/readiness";

export interface ReadinessBadgeProps {
  /**
   * 接受 generated.ts 的 SongResponse 9 字段（不强制 import 整个类型，
   * 让本组件独立可测、可被任何视图接入）。
   * undefined 视为空串或 null（与 evaluateReadiness 行为一致）。
   */
  song: {
    tabs?: string;
    lyrics_plain?: string;
    lyrics_lrc?: string;
    audio_vocal_path?: string | null;
    key?: string;
  };
  /** 'xs' = 9px（行内紧凑）/ 'sm' = 10px（D 区就绪度报告用） */
  size?: "xs" | "sm";
  dark: boolean;
  className?: string;
}

/** 单枚徽章的渲染：绿勾 or 灰叉 + 字段标签。 */
function Chip({ field, ready, size, dark }: { field: ReadinessField; ready: boolean; size: "xs" | "sm"; dark: boolean }) {
  const label = READINESS_FIELDS_LOOKUP[field];
  const fontSize = size === "xs" ? "9px" : "10px";
  const padding = size === "xs" ? "px-1" : "px-1.5";
  // 已就绪 → 绿（emerald，已通过 R5c 视觉测试）；缺失 → 中性灰
  const toneClass = ready
    ? dark
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : "bg-emerald-50 text-emerald-700 border-emerald-300/60"
    : dark
      ? "bg-zinc-800/60 text-zinc-500 border-zinc-700/60 line-through decoration-zinc-600"
      : "bg-muted/60 text-muted-foreground/70 border-border line-through decoration-muted-foreground/40";
  return (
    <span
      data-testid={`readiness-chip-${field}`}
      data-ready={ready ? "true" : "false"}
      title={ready ? `${label} · 就绪` : `${label} · 缺失`}
      aria-label={`${label} ${ready ? "已就绪" : "缺失"}`}
      className={`inline-flex items-center gap-0.5 ${padding} rounded border tabular-nums ${toneClass}`}
      style={{ fontSize }}
    >
      <span aria-hidden="true">{ready ? "✓" : "✗"}</span>
      <span>{label}</span>
    </span>
  );
}

/** 4 枚徽章容器。 */
export default function ReadinessBadge({ song, size = "xs", dark, className = "" }: ReadinessBadgeProps) {
  // 内部窄化：undefined → 空串 / null
  const normalized = {
    tabs: song.tabs ?? "",
    lyrics_plain: song.lyrics_plain ?? "",
    lyrics_lrc: song.lyrics_lrc ?? "",
    audio_vocal_path: song.audio_vocal_path ?? null,
    key: song.key ?? "",
  };
  const missing = evaluateReadiness(normalized);
  const missingSet = new Set(missing);
  return (
    <span
      data-testid="readiness-badge"
      data-ready-count={4 - missing.length}
      data-total-count={4}
      className={`inline-flex items-center gap-0.5 ${className}`}
      role="group"
      aria-label={`就绪度 ${4 - missing.length} / 4`}
    >
      {READINESS_FIELDS.map((field) => (
        <Chip key={field} field={field} ready={!missingSet.has(field)} size={size} dark={dark} />
      ))}
    </span>
  );
}
