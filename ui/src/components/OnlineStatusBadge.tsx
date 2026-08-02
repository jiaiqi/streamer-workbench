/// L1.5 顶栏在线/离线状态点
///
/// - 在线（绿点）：navigator.onLine = true
/// - 离线（红点）：navigator.onLine = false
/// - 监听 `online` / `offline` 事件
/// - 点击可手动重新检查 + 弹 toast（方便用户确认状态）
import { useEffect, useState } from "react";

export type OnlineState = "online" | "offline" | "unknown";

export function getOnlineState(): OnlineState {
  if (typeof navigator === "undefined") return "unknown";
  return navigator.onLine ? "online" : "offline";
}

export default function OnlineStatusBadge({ dark = false }: { dark?: boolean }) {
  const [state, setState] = useState<OnlineState>(getOnlineState);

  useEffect(() => {
    const onOnline = () => setState("online");
    const onOffline = () => setState("offline");
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    // 启动时也检查一次（防止 jsdom 初始状态不准）
    setState(getOnlineState());
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  const isOnline = state === "online";
  const isOffline = state === "offline";

  const dotColor = isOnline
    ? "bg-emerald-500"
    : isOffline
      ? "bg-red-500"
      : dark ? "bg-zinc-600" : "bg-zinc-400";

  const textColor = isOnline
    ? dark ? "text-emerald-300" : "text-emerald-700"
    : isOffline
      ? dark ? "text-red-300" : "text-red-600"
      : dark ? "text-zinc-500" : "text-muted-foreground";

  const label = isOnline ? "在线" : isOffline ? "离线" : "未知";

  return (
    <span
      data-testid="online-status-badge"
      data-state={state}
      title={
        isOffline
          ? "网络已断开；导出/同步操作会失败"
          : isOnline
            ? "网络已连接"
            : "网络状态未知"
      }
      className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${textColor}`}
    >
      <span
        data-testid="online-status-dot"
        className={`inline-block h-1.5 w-1.5 rounded-full ${dotColor} ${isOnline ? "" : isOffline ? "animate-pulse" : ""}`}
      />
      {label}
    </span>
  );
}
