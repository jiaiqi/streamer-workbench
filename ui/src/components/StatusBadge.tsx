/// R4.1.3 StatusBadge 统一状态徽章。
///
/// 取代散落的：
///   - PostersSidebar STATUS_LABEL + STATUS_COLOR (saved/dirty/saving/error)
///   - StatsView MetricCard 9 卡片（active_songs / draft_songs / total_events ...）
///   - LiveView 会话 state（active/closed）
///   - StatsView 队列 state（pending/queued/sung/...）
///
/// kind 决定色调；label 决定文案；icon 决定小图标
import type { ReactNode } from "react";

export type StatusKind =
  | "saved"
  | "dirty"
  | "saving"
  | "error"
  | "active"
  | "closed"
  | "draft"
  | "neutral"
  | "success";

export interface StatusBadgeProps {
  kind: StatusKind;
  /** 自定义文案（默认按 kind 查） */
  label?: string;
  /** 是否小尺寸（无 padding） */
  compact?: boolean;
  /** 暗色模式（自动从外观派生；不传则中性） */
  dark?: boolean;
  className?: string;
  /** 自定义 testid */
  "data-testid"?: string;
}

const DEFAULT_LABEL: Record<StatusKind, string> = {
  saved: "已保存",
  dirty: "编辑中",
  saving: "保存中",
  error: "失败",
  active: "进行中",
  closed: "已结束",
  draft: "未会",
  neutral: "—",
  success: "成功",
};

const KIND_CLASS: Record<StatusKind, { light: string; dark: string }> = {
  // saved / neutral / closed / draft → 中性灰
  saved:    { light: "bg-zinc-100 text-zinc-600",         dark: "bg-zinc-800/60 text-zinc-400" },
  neutral:  { light: "bg-zinc-100 text-zinc-600",         dark: "bg-zinc-800/60 text-zinc-400" },
  closed:   { light: "bg-zinc-100 text-zinc-600",         dark: "bg-zinc-800/60 text-zinc-400" },
  draft:    { light: "bg-zinc-100 text-zinc-600",         dark: "bg-zinc-800/60 text-zinc-400" },
  // active / saving / dirty → 主色
  active:   { light: "bg-emerald-50 text-emerald-700",    dark: "bg-emerald-500/15 text-emerald-300" },
  saving:   { light: "bg-emerald-50 text-emerald-700",    dark: "bg-emerald-500/15 text-emerald-300" },
  dirty:    { light: "bg-amber-50 text-amber-700",        dark: "bg-amber-500/15 text-amber-300" },
  // success → 主色（亮一点）
  success:  { light: "bg-emerald-50 text-emerald-700",    dark: "bg-emerald-500/15 text-emerald-300" },
  // error → 危险
  error:    { light: "bg-red-50 text-red-700",            dark: "bg-red-500/15 text-red-300" },
};

export default function StatusBadge({
  kind, label, compact, dark, className = "", "data-testid": testId,
}: StatusBadgeProps) {
  const text = label ?? DEFAULT_LABEL[kind];
  const palette = KIND_CLASS[kind];
  const paletteClass = dark ? palette.dark : palette.light;
  return (
    <span
      data-testid={testId}
      data-status={kind}
      className={`inline-flex items-center gap-1 rounded-full text-[11px] font-medium tabular-nums ${
        compact ? "px-1.5 py-0.5" : "px-2 py-0.5"
      } ${paletteClass} ${className}`}
    >
      <span
        aria-hidden="true"
        className={`inline-block w-1.5 h-1.5 rounded-full ${
          kind === "active" || kind === "saving" || kind === "success" ? "animate-pulse" : ""
        }`}
        style={{
          background:
            kind === "error" ? "currentColor"
            : kind === "dirty" ? "currentColor"
            : kind === "active" || kind === "saving" || kind === "success" ? "currentColor"
            : "currentColor",
          opacity: 0.6,
        }}
      />
      {text}
    </span>
  );
}
