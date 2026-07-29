import type { RequestFailure } from "../async/requestState";

export default function AsyncStateNotice({ kind, error, onRetry, label = "内容" }: {
  kind: "loading" | "empty" | "error";
  error?: RequestFailure | null;
  onRetry?: () => void;
  label?: string;
}) {
  if (kind === "loading") return <div className="state-panel" role="status" aria-live="polite"><span className="spinner" />正在加载{label}…</div>;
  if (kind === "empty") return <div className="state-panel">还没有{label}</div>;
  return (
    <div className="state-panel state-error" role="alert">
      <strong>{error?.message ?? `${label}加载失败`}</strong>
      {error?.recovery && <span>{error.recovery}</span>}
      {error?.requestId && <small>请求编号：{error.requestId}</small>}
      {onRetry && <button type="button" className="secondary-action" onClick={onRetry}>重试</button>}
    </div>
  );
}
