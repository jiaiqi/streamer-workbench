/// M9.6b 全局 toast 系统 — 5 秒撤销兜底
///
/// 设计目标：
///   - 全局唯一 ToastProvider，App 顶层包（与 PlayerProvider 同级）
///   - useToast() hook 暴露 show / dismiss
///   - 单条 toast：message + 可选 action（撤销/重试等）+ durationMs
///   - 固定底栏常驻；多条垂直堆叠
///   - 自动消失（durationMs 到期）；✕ 手动关闭
///   - 撤销按钮：点击 → 调 onClick → toast 立即消失
///
/// MVP 范围（M9.6b）：只接入 LibraryView 删除 → 撤销恢复
/// 未来可扩展：所有破坏性操作（preset 删除、session 关闭、批量操作等）
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export interface ToastAction {
  label: string;
  onClick: () => void | Promise<void>;
  /** action 变体：撤销用 primary，重试用 warning */
  variant?: "primary" | "warning" | "neutral";
}

export interface ToastInput {
  message: string;
  action?: ToastAction;
  /** 自动消失毫秒数；0 = 不自动消失（需手动 ✕）；默认 5000 */
  durationMs?: number;
}

interface ToastItem extends ToastInput {
  id: string;
  /** 注入：用于倒计时显示剩余秒数 */
  createdAt: number;
}

interface ToastApi {
  show: (input: ToastInput) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const ToastContext = createContext<ToastApi | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems(prev => prev.filter(it => it.id !== id));
    const t = timersRef.current.get(id);
    if (t) {
      clearTimeout(t);
      timersRef.current.delete(id);
    }
  }, []);

  const show = useCallback((input: ToastInput): string => {
    const id = `t${nextId++}`;
    const duration = input.durationMs ?? 5000;
    const item: ToastItem = { ...input, id, createdAt: Date.now() };
    setItems(prev => [...prev, item]);
    if (duration > 0) {
      const t = setTimeout(() => dismiss(id), duration);
      timersRef.current.set(id, t);
    }
    return id;
  }, [dismiss]);

  const clear = useCallback(() => {
    setItems([]);
    timersRef.current.forEach(t => clearTimeout(t));
    timersRef.current.clear();
  }, []);

  // 卸载时清掉所有 timer
  useEffect(() => {
    return () => {
      timersRef.current.forEach(t => clearTimeout(t));
      timersRef.current.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ show, dismiss, clear }}>
      {children}
      <ToastViewport items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

/* ---- 视图：固定底栏堆叠 ---- */
function ToastViewport({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <div
      data-testid="toast-viewport"
      aria-live="polite"
      aria-atomic="false"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-col-reverse items-center gap-2 pointer-events-none"
    >
      {items.map(item => (
        <ToastCard key={item.id} item={item} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  const [remainingMs, setRemainingMs] = useState(
    item.durationMs && item.durationMs > 0 ? item.durationMs : 0,
  );
  const [busy, setBusy] = useState(false);

  // 倒计时：每秒 -1s（仅在有 durationMs 时）
  useEffect(() => {
    if (!item.durationMs || item.durationMs <= 0) return;
    const id = setInterval(() => {
      setRemainingMs(prev => {
        const next = prev - 1000;
        return next < 0 ? 0 : next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [item.durationMs]);

  const handleAction = async () => {
    if (!item.action || busy) return;
    setBusy(true);
    try {
      await item.action.onClick();
    } catch {
      /* action 失败不阻止 toast 关闭（避免无限循环） */
    } finally {
      setBusy(false);
      onDismiss(item.id);
    }
  };

  const variant = item.action?.variant ?? "primary";
  const actionStyle = variant === "primary"
    ? "text-emerald-300 hover:text-emerald-200"
    : variant === "warning"
      ? "text-amber-300 hover:text-amber-200"
      : "text-zinc-300 hover:text-zinc-100";

  const remainingSec = Math.ceil(remainingMs / 1000);

  return (
    <div
      data-testid="toast-item"
      data-toast-id={item.id}
      role="status"
      className="pointer-events-auto flex items-center gap-3 rounded-lg bg-zinc-900/95 px-4 py-2.5 text-sm text-zinc-100 shadow-lg backdrop-blur-md border border-zinc-700/60 min-w-[280px] max-w-[420px]"
    >
      <span data-testid="toast-message" className="flex-1 min-w-0 truncate">
        {item.message}
      </span>
      {item.action && (
        <button
          type="button"
          data-testid="toast-action"
          onClick={handleAction}
          disabled={busy}
          className={`shrink-0 font-semibold transition-colors cursor-pointer disabled:opacity-50 ${actionStyle}`}
        >
          {item.action.label}
        </button>
      )}
      {item.durationMs && item.durationMs > 0 && (
        <span data-testid="toast-remaining" className="shrink-0 tabular-nums text-xs text-zinc-500">
          {remainingSec}s
        </span>
      )}
      <button
        type="button"
        data-testid="toast-close"
        onClick={() => onDismiss(item.id)}
        aria-label="关闭"
        className="shrink-0 text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
      >
        ✕
      </button>
    </div>
  );
}
