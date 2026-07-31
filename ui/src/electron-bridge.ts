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
