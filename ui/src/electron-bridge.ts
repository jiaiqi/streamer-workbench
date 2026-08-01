/// Electron preload 暴露的 window.streamer API 类型与跨平台调用工具。
///
/// 浏览器中 window.streamer 不存在 → 走 window.open(target=_blank)
/// Electron 中 window.streamer 存在 → 拦截默认行为，调用 IPC 开置顶速查子窗口
declare global {
  interface Window {
    streamer?: {
      openQuickView(sessionId?: string): Promise<{ ok: boolean }>;
      closeQuickView(): Promise<{ ok: boolean }>;
      onQuickViewSession(listener: (sessionId: string) => void): () => void;
    };
  }
}

export const isElectron = (): boolean =>
  typeof window !== "undefined" && typeof window.streamer === "object";

/**
 * 打开直播速查窗口。
 * @param sessionId LiveSession id（Electron 下透传给子窗口；浏览器下作为 URL query）
 * @param e 若提供 React 事件且处于 Electron 模式，会阻止默认行为避免开新 tab
 */
export function openQuickView(
  sessionId?: string,
  e?: { preventDefault?: () => void },
): void {
  if (isElectron()) {
    e?.preventDefault?.();
    void window.streamer!.openQuickView(sessionId);
    return;
  }
  // 浏览器模式：让外层 <a target="_blank"> 走默认行为
  // 此函数不主动调用，调用方应使用 <a> 让浏览器打开
}

/**
 * R2.5: 渲染并打开直播复盘海报 PNG。
 * @param sessionId LiveSession id
 * @param baseUrl API 根（默认当前 origin）
 * @param authToken 会话令牌（packaged 模式需要）
 */
export async function openLivePoster(
  sessionId: string,
  baseUrl: string = window.location.origin,
  authToken: string = "",
): Promise<void> {
  const headers: Record<string, string> = {};
  if (authToken) headers["X-Session-Token"] = authToken;
  const res = await fetch(
    `${baseUrl}/api/live-sessions/${encodeURIComponent(sessionId)}/poster`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify({
        theme_id: "海洋柔光",
        canvas_id: "抖音全屏 9:20",
      }),
    },
  );
  if (!res.ok) {
    throw new Error(`live-set 海报渲染失败：HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank", "noopener,noreferrer");
  // 浏览器在 window 被关时自动释放；Electron popup blocker 兜底
  if (!w) {
    console.warn("openLivePoster: 浏览器拦截了新窗口打开");
  }
  // 30 秒后释放 blob URL（足够用户操作）
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
