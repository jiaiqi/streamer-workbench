import type { RequestFailure } from "../async/requestState";

export default function AsyncStateNotice({ kind, error, onRetry, label = "内容", actionLabel, onAction, actionPending }: {
  kind: "loading" | "empty" | "error";
  error?: RequestFailure | null;
  onRetry?: () => void;
  label?: string;
  actionLabel?: string;
  onAction?: () => void;
  actionPending?: boolean;
}) {
  if (kind === "loading") return <div className="state-panel" role="status" aria-live="polite"><span className="spinner" />正在加载{label}…</div>;
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
