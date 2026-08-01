/// R4.1.1 EmptyState 统一空态组件。
///
/// 取代散落的：
///   - <AsyncStateNotice kind="empty" /> 简化版
///   - <div className="panel-empty">...</div> 自写
///   - <EmptyNotice note={...} /> StatsView 自写
///
/// 形态：图标 + 标题 + 描述 + 可选 action
/// 布局：垂直居中；可选 `inline` 改为水平紧凑版
import type { ReactNode } from "react";

export interface EmptyStateProps {
  /** 大图标（emoji / 24px 内的 icon），可选 */
  icon?: ReactNode;
  /** 标题（必填，1 行） */
  title: string;
  /** 描述（可选，2-3 行） */
  description?: ReactNode;
  /** 行为按钮文案 */
  actionLabel?: string;
  /** 行为回调 */
  onAction?: () => void;
  /** 行为按钮 loading 状态 */
  actionPending?: boolean;
  /** 次要按钮文案（互斥 with action） */
  secondaryLabel?: string;
  /** 次要按钮回调 */
  onSecondary?: () => void;
  /** 紧凑模式（用于列表/侧栏；不撑满高度） */
  inline?: boolean;
  /** 暗色模式 */
  dark?: boolean;
  /** 自定义 testid */
  "data-testid"?: string;
}

export default function EmptyState({
  icon, title, description,
  actionLabel, onAction, actionPending,
  secondaryLabel, onSecondary,
  inline, dark,
  "data-testid": testId,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      data-testid={testId}
      className={`empty-state flex flex-col items-center text-center px-4 py-6 ${
        inline ? "gap-1.5" : "gap-3 min-h-[140px] justify-center"
      } ${dark ? "text-zinc-400" : "text-muted-foreground"}`}
    >
      {icon && <div className="empty-state-icon" aria-hidden="true">{icon}</div>}
      <p className="text-sm font-medium">{title}</p>
      {description && (
        <p className={`text-xs max-w-[36ch] leading-relaxed ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          {description}
        </p>
      )}
      {(actionLabel || secondaryLabel) && (
        <div className="flex items-center gap-2 mt-1">
          {actionLabel && onAction && (
            <button
              type="button"
              onClick={onAction}
              disabled={actionPending}
              aria-busy={actionPending}
              data-loading={actionPending ? "true" : "false"}
              className="secondary-action"
            >
              {actionPending ? "载入中…" : actionLabel}
            </button>
          )}
          {secondaryLabel && onSecondary && (
            <button
              type="button"
              onClick={onSecondary}
              className="ghost-action"
            >
              {secondaryLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
