/// R4.0.12 海报真保存路径 — 跨 Electron / 浏览器的统一保存 API。
///
/// 行为：
///   - Electron（window.streamer.saveFile 存在）：IPC 弹原生 dialog.showSaveDialog，主进程写盘
///   - 浏览器：<a download> 触发下载
///   - 都不可用：fallback 抛错（不应发生）
///
/// 返回：
///   { ok: true, path?, method: 'native' | 'download' }
///   { ok: false, cancelled?: boolean, error?: string }
export interface SaveFileSuccess {
  ok: true;
  /** Electron 下是真实保存路径；浏览器下为 null。 */
  path: string | null;
  /** 走的是哪条路径：native dialog 还是浏览器 download。 */
  method: "native" | "download";
  /** defaultName（便于上层 toast 提示）。 */
  filename: string;
}
export interface SaveFileFailure {
  ok: false;
  cancelled?: boolean;
  error?: string;
}
export type SaveFileResult = SaveFileSuccess | SaveFileFailure;

interface ElectronSaveFile {
  (params: { data: ArrayBuffer; defaultName: string; mimeType?: string })
    : Promise<{ ok: boolean; path?: string; cancelled?: boolean; error?: string }>;
}

declare global {
  interface Window {
    streamer?: {
      saveFile?: ElectronSaveFile;
      [key: string]: unknown;
    };
  }
}

/**
 * 触发浏览器下载 <a download>。同步创建 → 模拟点击 → 异步清理。
 * 不依赖任何外部状态。
 */
function browserDownload(blob: Blob, defaultName: string): SaveFileSuccess {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = defaultName;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  // 给浏览器一点时间触发下载再清理
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 1000);
  return { ok: true, path: null, method: "download", filename: defaultName };
}

/**
 * 把 Blob 持久化保存（走 Electron 原生对话框或浏览器 <a download>）。
 */
export async function saveBlob(blob: Blob, defaultName: string): Promise<SaveFileResult> {
  if (!blob) return { ok: false, error: "empty blob" };
  if (!defaultName) return { ok: false, error: "empty defaultName" };

  // Electron 路径
  const streamer = typeof window !== "undefined" ? window.streamer : undefined;
  if (streamer?.saveFile) {
    try {
      const buffer = await blob.arrayBuffer();
      const res = await streamer.saveFile({
        data: buffer,
        defaultName,
        mimeType: blob.type || undefined,
      });
      if (res.cancelled) return { ok: false, cancelled: true };
      if (!res.ok) return { ok: false, error: res.error || "save failed" };
      return { ok: true, path: res.path ?? null, method: "native", filename: defaultName };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : "save failed" };
    }
  }

  // 浏览器路径
  try {
    return browserDownload(blob, defaultName);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "browser download failed" };
  }
}

/** 工具：把 fetch Response 转 Blob，并复用 response URL 作为 hint。 */
export async function responseToBlob(res: Response): Promise<Blob> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.blob();
}
