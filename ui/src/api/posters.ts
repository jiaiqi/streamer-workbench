/// P1 R1a 前端 API 客户端包装：海报文档 + RenderDocument 预览/导出。
///
/// 全部函数均通过 `apiRequest` 自动处理：
/// - 网络/超时错误 → ApiClientError
/// - 后端 ApiError envelope → ApiClientError（含 code/recovery）
/// - AbortSignal 取消 → 透传 rejection
///
/// 业务方可在 React Query / 自写 useState 中调用；本模块不绑定状态管理。
import type {
  PosterRequest,
  PosterResponse,
  PosterResolveResponse,
  PosterSaveResponse,
  PosterSummaryResponse,
  RenderDocumentRequest,
  RenderDocumentResponse,
} from "./generated";
import { apiRequest } from "./client";

// ── 海报文档 (CRUD + 解析) ────────────────────────────────────

export function listPosters(): Promise<PosterSummaryResponse[]> {
  return apiRequest<PosterSummaryResponse[]>("/api/posters");
}

// ── R4 Runtime v2 v2.5: Theme × Layout 能力矩阵 ──

export interface CompatibilityCheckResult {
  compatible: boolean;
  reason: string;
}

export interface CompatibilityMatrix {
  layouts: string[];
  themes: string[];
  matrix: Record<string, Record<string, CompatibilityCheckResult>>;
}

export function checkCompatibility(
  layoutId: string,
  themeId: string,
): Promise<CompatibilityCheckResult> {
  return apiRequest<CompatibilityCheckResult>(
    `/api/compatibility?layout_id=${encodeURIComponent(layoutId)}&theme_id=${encodeURIComponent(themeId)}`,
  );
}

export function getCompatibilityMatrix(): Promise<CompatibilityMatrix> {
  return apiRequest<CompatibilityMatrix>("/api/compatibility/matrix");
}

export function getCompatibleLayoutsForTheme(themeId: string): Promise<{ items: string[] }> {
  return apiRequest<{ items: string[] }>(
    `/api/compatibility/layouts?theme_id=${encodeURIComponent(themeId)}`,
  );
}

export function getCompatibleThemesForLayout(layoutId: string): Promise<{ items: string[] }> {
  return apiRequest<{ items: string[] }>(
    `/api/compatibility/themes?layout_id=${encodeURIComponent(layoutId)}`,
  );
}

export function getPoster(posterId: string): Promise<PosterResponse> {
  return apiRequest<PosterResponse>(`/api/posters/${posterId}`);
}

export function savePoster(payload: PosterRequest): Promise<PosterSaveResponse> {
  // POST /api/posters: 创建(id 缺)/整体覆盖(有 id)
  return apiRequest<PosterSaveResponse>("/api/posters", {
    method: "POST",
    body: payload,
  });
}

export function deletePoster(
  posterId: string,
): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/api/posters/${posterId}`, {
    method: "DELETE",
  });
}

// ── M3 P1 批量操作 ────────────────────────────────────────────

export type PosterBatchAction = "delete" | "duplicate" | "set_theme" | "reorder";

export interface PosterBatchRequest {
  action: PosterBatchAction;
  ids: string[];
  /** 仅 set_theme 时必填；其他 action 忽略。 */
  theme?: string;
}

export interface PosterBatchResponse {
  ok: boolean;
  action: PosterBatchAction;
  /** delete 成功数 */
  deleted?: number;
  /** duplicate 成功数 */
  duplicated?: number;
  /** set_theme 成功数 */
  updated?: number;
  /** reorder 成功数 */
  reordered?: number;
  /** duplicate 新生成的 id 列表（顺序对应 ids） */
  new_ids?: string[];
  /** 部分失败明细（id + error） */
  failed: { id: string; error: string }[];
}

export function batchPosters(
  payload: PosterBatchRequest,
): Promise<PosterBatchResponse> {
  return apiRequest<PosterBatchResponse>("/api/posters/batch", {
    method: "POST",
    body: payload,
  });
}

export function resolvePoster(
  posterId: string,
): Promise<PosterResolveResponse> {
  return apiRequest<PosterResolveResponse>(
    `/api/posters/${posterId}/resolve`,
    { method: "POST" },
  );
}

// ── RenderDocument (预览/导出共享输入) ─────────────────────────

export function buildRenderDocument(
  payload: RenderDocumentRequest,
  signal?: AbortSignal,
): Promise<RenderDocumentResponse> {
  return apiRequest<RenderDocumentResponse>("/api/render/document", {
    method: "POST",
    body: payload,
    signal,
  });
}

export function renderDocumentImageUrl(
  payload: RenderDocumentRequest,
): string {
  // P1 R1a.8 预览缓存治理：URL 用结构化查询（不含 &t=），
  // 由后端在响应里给 document_id 决定缓存键；前端以 document_id 决定是否重渲染。
  // 此处仍是 GET-friendly 字符串，但实际服务端是 POST → 客户端改为 fetch 调用。
  void payload;
  // 注意：P1 后端是 POST；这个 helper 返回 string 仅保留在 UI 调试期。
  return "/api/render/document/image";
}

export async function fetchRenderDocumentImage(
  payload: RenderDocumentRequest,
  signal?: AbortSignal,
): Promise<Blob> {
  // 直接 fetch（不走 typed apiRequest）因为返回二进制
  const res = await fetch("/api/render/document/image", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    let err: unknown;
    try { err = await res.json(); } catch { /* not JSON */ }
    throw new Error(`render failed: ${res.status} ${JSON.stringify(err)}`);
  }
  return res.blob();
}

// ── 海报类型化辅助（SongSource/PagePolicy/ExportSettings 等都在 generated） ──

export type SongSourceType = "all_active" | "manual" | "artist";

export interface PosterSourceUI {
  type: SongSourceType;
  artists: string[];
}

export interface PosterPolicyUI {
  mode: "legacy-fixed-2" | "auto" | "manual";
  minPages?: number | null;
  maxPages?: number | null;
  manualPages: Array<Record<string, unknown>>;
}

export interface PosterExportSettingsUI {
  format: "png" | "jpeg";
  jpegQuality: number;
  singlePage: boolean;
  dpi: number;
}

// ── L2.2 批量按 ID 导出 ─────────────────────────────

export interface ExportByIdsArgs {
  theme: string;
  song_ids: string[];
  layout?: string;
  canvas?: string;
  avoid?: boolean;
}

export interface ExportByIdsFileResult {
  song_id: string;
  title: string;
  path: string;
  filename: string;
  duration_ms: number | null;
}

export interface ExportByIdsResult {
  ok: boolean;
  total: number;
  total_ms: number | null;
  files: ExportByIdsFileResult[];
}

/** 同步执行：每首选中歌曲渲染成 1 张 PNG 存到 settings.output_dir。 */
export function exportBySongIds(args: ExportByIdsArgs): Promise<ExportByIdsResult> {
  return apiRequest<ExportByIdsResult>("/api/export/by-ids", {
    method: "POST",
    body: {
      theme: args.theme,
      song_ids: args.song_ids,
      layout: args.layout ?? "grid-wrap",
      canvas: args.canvas ?? "标准 9:16",
      avoid: args.avoid ?? true,
    },
  });
}

// ── L2.3 曲库导入导出 ─────────────────────────────

export function exportLibrary(): Promise<SongExportResponse> {
  return apiRequest<SongExportResponse>("/api/songs/export");
}

export function importLibrary(
  body: SongImportRequestBody,
): Promise<SongImportResultResponse> {
  return apiRequest<SongImportResultResponse>("/api/songs/import", {
    method: "POST",
    body,
  });
}

// ── L2.3 快照 ─────────────────────────────

export function listSnapshots(): Promise<SnapshotListResponse> {
  return apiRequest<SnapshotListResponse>("/api/songs/snapshots");
}

export function restoreSnapshot(filename: string): Promise<{ ok: boolean; filename: string }> {
  return apiRequest<{ ok: boolean; filename: string }>(
    "/api/songs/snapshots/restore",
    { method: "POST", body: { filename } },
  );
}
