/// Electron preload 暴露的 window.streamer API 类型与跨平台调用工具。
///
/// 类型定义在 `lib/streamer.ts` 统一声明，本文件只放跨平台调用工具函数。
/// 浏览器中 window.streamer 不存在 → 浏览器 <a download> 路径
/// Electron 中 window.streamer 存在 → IPC 弹原生保存对话框（R4.0.12）
import "./lib/streamer";

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
    void window.streamer?.openQuickView?.(sessionId);
    return;
  }
  // 浏览器模式：让外层 <a target="_blank"> 走默认行为
  // 此函数不主动调用，调用方应使用 <a> 让浏览器打开
}

/* ---- R4.0.12 海报真保存：抽到 lib/saveFile.ts ---- */
import { saveBlob, type SaveFileResult } from "./lib/saveFile";

/** 文件名辅助：直播复盘海报 */
function livePosterFilename(sessionId: string): string {
  const date = new Date();
  const stamp = `${date.getFullYear()}${(date.getMonth() + 1).toString().padStart(2, "0")}${date.getDate().toString().padStart(2, "0")}`;
  return `复盘海报-${sessionId.slice(0, 8)}-${stamp}.png`;
}

/** 文件名辅助：学歌报告 */
function learningReportFilename(days: number, label: string): string {
  const date = new Date();
  const stamp = `${date.getFullYear()}${(date.getMonth() + 1).toString().padStart(2, "0")}${date.getDate().toString().padStart(2, "0")}`;
  const safeLabel = label ? label.replace(/[\\/:*?"<>|]/g, "_") : `${days}天`;
  return `学歌报告-${safeLabel}-${stamp}.png`;
}

/**
 * R2.5: 渲染并保存直播复盘海报 PNG。
 * Electron 走原生保存对话框；浏览器走 <a download>。
 * @param sessionId LiveSession id
 * @param baseUrl API 根（默认当前 origin）
 * @param authToken 会话令牌（packaged 模式需要）
 * @returns SaveFileResult — caller 可用于 toast 提示「已保存到 xxx」
 */
export async function openLivePoster(
  sessionId: string,
  baseUrl: string = window.location.origin,
  authToken: string = "",
): Promise<SaveFileResult> {
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
  return await saveBlob(blob, livePosterFilename(sessionId));
}

/**
 * R3.5: 渲染并保存学歌报告海报 PNG。
 * @param options days / period_label / top_n_artists
 * @param baseUrl API 根
 * @param authToken 会话令牌（packaged 模式需要）
 */
export async function openLearningReportPoster(
  options: { days?: number; period_label?: string; top_n_artists?: number } = {},
  baseUrl: string = window.location.origin,
  authToken: string = "",
): Promise<SaveFileResult> {
  const days = options.days ?? 30;
  const label = options.period_label ?? `${days}天`;
  const headers: Record<string, string> = {};
  if (authToken) headers["X-Session-Token"] = authToken;
  const res = await fetch(
    `${baseUrl}/api/learning-report/poster`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify({
        theme_id: "海洋柔光",
        canvas_id: "抖音全屏 9:20",
        days,
        period_label: label,
        top_n_artists: options.top_n_artists ?? 5,
      }),
    },
  );
  if (!res.ok) {
    throw new Error(`learning-report 海报渲染失败：HTTP ${res.status}`);
  }
  const blob = await res.blob();
  return await saveBlob(blob, learningReportFilename(days, label));
}
