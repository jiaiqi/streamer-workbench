import type { RequestFailure } from "../async/requestState";
import Spinner from "./Spinner";

export default function AsyncStateNotice({ kind, error, onRetry, label = "内容", actionLabel, onAction, actionPending }: {
  kind: "loading" | "empty" | "error";
  error?: RequestFailure | null;
  onRetry?: () => void;
  label?: string;
  actionLabel?: string;
  onAction?: () => void;
  actionPending?: boolean;
}) {
  if (kind === "loading") {
    return (
      <div className="state-panel" role="status" aria-live="polite">
        {/* 3.1 收口：原 <span className="spinner" /> 改用 Spinner 组件 */}
        <Spinner size="sm" tone="current" decorative label={`正在加载${label}`} />
        <span>正在加载{label}…</span>
      </div>
    );
  }
  if (kind === "empty") {
    return (
      <div className="state-panel" role="status">
        <span>还没有{label}</span>
        {actionLabel && onAction && (
          <button
            type="button"
            className="secondary-action"
            onClick={onAction}
            disabled={actionPending}
            aria-busy={actionPending}
          >
            {actionPending ? "载入中…" : actionLabel}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="state-panel state-error" role="alert">
      <strong>{error?.message ?? `${label}加载失败`}</strong>
      {error?.recovery && <span>{error.recovery}</span>}
      {error?.requestId && <small>请求编号：{error.requestId}</small>}
      {onRetry && <button type="button" className="secondary-action" onClick={onRetry}>重试</button>}
    </div>
  );
}
