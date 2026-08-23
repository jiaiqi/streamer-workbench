/// P1-A2: SongActionBar — 5 动作底部条
///
/// 设计：与 L2.1 批量操作 bar 并存，**不替换**。两 bar 在 select 模式下同时显示：
///   - L2.1 bar：批量改状态、批量删除、批量导出（库内自洽操作）
///   - SongActionBar：跨视图动作（去海报/直播/学习/弹唱/编辑）
///
/// 5 动作（顺序稳定，UI 徽标颜色递减强度）：
///   1. 加入当前海报   — emerald（主调）
///   2. 加入今晚歌单   — rose（暖调）
///   3. 加入学习计划   — sky（冷调）
///   4. ▶ 弹唱         — zinc（中性）
///   5. ✏️ 编辑         — zinc（中性）
///
/// disabled 规则：
///   - hasCurrentPoster=false  → 按钮 1 disabled（无当前海报）
///   - hasActiveSession=false  → 按钮 2 disabled（无活跃直播）
///   - titles.length===0       → 所有按钮 disabled
///
/// 零外部依赖 — 纯受控 props。
import type { ReactNode } from "react";

export interface SongActionBarProps {
  /** 已选歌曲数；0 时整条隐藏/全 disabled。 */
  selectedCount: number;
  /** Library 视图是否在 dark 模式（与现有 batch bar 配色一致）。 */
  dark: boolean;
  /** 当前是否有正在编辑的海报（无则按钮 1 disabled）。 */
  hasCurrentPoster: boolean;
  /** 当前是否有活跃直播 session（无则按钮 2 disabled）。 */
  hasActiveSession: boolean;
  onAddToCurrentPoster: () => void;
  onAddToTonightSession: () => void;
  onAddToLearningPlan: () => void;
  onPlay: () => void;
  onEdit: () => void;
}

interface ActionDef {
  testId: string;
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled: boolean;
  /** 配色 hint："emerald" | "rose" | "sky" | "zinc" */
  tone: "emerald" | "rose" | "sky" | "zinc";
  /** tooltip 解释 disabled 原因。 */
  disabledHint?: string;
}

const ICON_PLUS = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
    aria-hidden="true">
    <path d="M12 5v14M5 12h14" />
  </svg>
);
const ICON_ROSE = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    aria-hidden="true">
    <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7Z" />
  </svg>
);
const ICON_BOOK = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    aria-hidden="true">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
  </svg>
);
const ICON_PLAY = <span aria-hidden="true">▶</span>;
const ICON_EDIT = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    aria-hidden="true">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

/** 给定 tone + dark，返回按钮的 4 段 class（常态 / hover / disabled）。 */
function toneClass(tone: ActionDef["tone"], dark: boolean): {
  base: string; hover: string; disabled: string;
} {
  if (tone === "emerald") {
    return dark
      ? { base: "bg-emerald-600 text-white border border-emerald-500",
          hover: "hover:bg-emerald-500",
          disabled: "disabled:bg-emerald-900/40 disabled:text-emerald-300/40 disabled:border-emerald-700/30" }
      : { base: "bg-emerald-600 text-white border border-emerald-600",
          hover: "hover:bg-emerald-700",
          disabled: "disabled:bg-emerald-200 disabled:text-emerald-400 disabled:border-emerald-200" };
  }
  if (tone === "rose") {
    return dark
      ? { base: "bg-rose-600/90 text-white border border-rose-500",
          hover: "hover:bg-rose-500",
          disabled: "disabled:bg-rose-900/40 disabled:text-rose-300/40 disabled:border-rose-700/30" }
      : { base: "bg-rose-600 text-white border border-rose-600",
          hover: "hover:bg-rose-700",
          disabled: "disabled:bg-rose-200 disabled:text-rose-400 disabled:border-rose-200" };
  }
  if (tone === "sky") {
    return dark
      ? { base: "bg-sky-600/90 text-white border border-sky-500",
          hover: "hover:bg-sky-500",
          disabled: "disabled:bg-sky-900/40 disabled:text-sky-300/40 disabled:border-sky-700/30" }
      : { base: "bg-sky-600 text-white border border-sky-600",
          hover: "hover:bg-sky-700",
          disabled: "disabled:bg-sky-200 disabled:text-sky-400 disabled:border-sky-200" };
  }
  // zinc
  return dark
    ? { base: "bg-zinc-800 text-zinc-200 border border-zinc-700",
        hover: "hover:bg-zinc-700",
        disabled: "disabled:bg-zinc-800/40 disabled:text-zinc-500 disabled:border-zinc-800/40" }
    : { base: "bg-background text-foreground border border-border",
        hover: "hover:bg-muted",
        disabled: "disabled:bg-muted/40 disabled:text-muted-foreground/40 disabled:border-border/60" };
}

function ActionButton({ def, dark }: { def: ActionDef; dark: boolean }) {
  const cls = toneClass(def.tone, dark);
  return (
    <button
      type="button"
      data-testid={def.testId}
      onClick={def.onClick}
      disabled={def.disabled}
      title={def.disabled && def.disabledHint ? def.disabledHint : undefined}
      aria-disabled={def.disabled}
      className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer ${cls.base} ${cls.hover} ${cls.disabled}`}
    >
      {def.icon}
      {def.label}
    </button>
  );
}

export default function SongActionBar({
  selectedCount,
  dark,
  hasCurrentPoster,
  hasActiveSession,
  onAddToCurrentPoster,
  onAddToTonightSession,
  onAddToLearningPlan,
  onPlay,
  onEdit,
}: SongActionBarProps) {
  if (selectedCount === 0) return null;

  const noSelection = selectedCount === 0;
  const actions: ActionDef[] = [
    {
      testId: "song-action-add-to-poster",
      label: "加入当前海报",
      icon: ICON_PLUS,
      onClick: onAddToCurrentPoster,
      disabled: noSelection || !hasCurrentPoster,
      disabledHint: hasCurrentPoster ? undefined : "先在工作台打开或新建一张海报",
      tone: "emerald",
    },
    {
      testId: "song-action-add-to-tonight",
      label: "加入今晚歌单",
      icon: ICON_ROSE,
      onClick: onAddToTonightSession,
      disabled: noSelection || !hasActiveSession,
      disabledHint: hasActiveSession ? undefined : "先到「直播」标签开一场今晚的歌单",
      tone: "rose",
    },
    {
      testId: "song-action-add-to-learning",
      label: "加入学习计划",
      icon: ICON_BOOK,
      onClick: onAddToLearningPlan,
      disabled: noSelection,
      tone: "sky",
    },
    {
      testId: "song-action-play",
      label: "弹唱",
      icon: ICON_PLAY,
      onClick: onPlay,
      disabled: noSelection,
      tone: "zinc",
    },
    {
      testId: "song-action-edit",
      label: "编辑",
      icon: ICON_EDIT,
      onClick: onEdit,
      disabled: noSelection || selectedCount > 1,
      disabledHint: selectedCount > 1 ? "编辑仅支持单选" : undefined,
      tone: "zinc",
    },
  ];

  return (
    <div
      data-testid="song-action-bar"
      aria-label="歌曲批量动作"
      className={`shrink-0 z-20 flex items-center gap-2 px-6 h-12 border-t ${
        dark ? "bg-zinc-900/95 border-zinc-700 backdrop-blur-sm"
             : "bg-background/95 border-border backdrop-blur-sm"
      }`}>
      <span
        data-testid="song-action-count"
        className={`text-[11px] uppercase tracking-widest font-semibold ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
        5 动作
      </span>
      <div className="ml-2 flex items-center gap-2 flex-wrap">
        {actions.map(a => <ActionButton key={a.testId} def={a} dark={dark} />)}
      </div>
    </div>
  );
}
