/// M2.9 在线元数据搜索选择对话框。
///
/// 流程：
/// 1. 打开后立即调 /api/metadata/search（keyword + type=song + limit=20）
/// 2. 列出 Hit 列表
/// 3. 用户点击某条 → 调 /api/metadata/song 拿 SongDetail
/// 4. onPick(detail) 回调给父组件填表单
///
/// 离线 / 错误：
/// - 离线时（L1.5 OnlineStatusBadge）按钮被父组件禁用，但这里也防御一下
/// - search 失败 → toast.error（M2.6 useApiError）+ 在弹窗内显示错误
/// - song 失败 → toast.error + 状态恢复可重试
///
/// 数据：只展示 song 类型，artist/album/playlist 推迟到 M2.11+。

import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { useApiError } from "../async/useApiError";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface MetadataHit {
  source: string;
  song_id: string;
  title: string;
  artist: string;
  album: string | null;
  duration_ms: number | null;
  cover_url: string | null;
}

export interface MetadataSongDetail {
  source: string;
  song_id: string;
  title: string;
  artist: string;
  artist_id: string | null;
  album: string | null;
  album_id: string | null;
  duration_ms: number;
  cover_url: string | null;
  bpm: number | null;
}

export interface MetadataSearchDialogProps {
  open: boolean;
  onClose: () => void;
  onPick: (detail: MetadataSongDetail) => void;
  keyword: string;
}

interface SearchResponse {
  keyword: string;
  type: string;
  provider: string | null;
  items: MetadataHit[];
}

const SEARCH_LIMIT = 20;

function formatDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function MetadataSearchDialog({
  open, onClose, onPick, keyword,
}: MetadataSearchDialogProps) {
  const { runWithToast } = useApiError();
  const [hits, setHits] = useState<MetadataHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [inlineError, setInlineError] = useState<string>("");

  // 打开时自动跑一次 search（keyword 变化时也重跑）
  useEffect(() => {
    if (!open) return;
    setInlineError("");
    const trimmed = (keyword || "").trim();
    if (!trimmed) {
      setHits([]);
      setSearched(true);
      return;
    }
    void runSearch(trimmed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, keyword]);

  const runSearch = async (kw: string) => {
    setSearching(true);
    setInlineError("");
    try {
      const data = await runWithToast(
        () => apiRequest<SearchResponse>("/api/metadata/search", {
          method: "POST",
          body: { keyword: kw, type: "song", limit: SEARCH_LIMIT },
        }),
        "在线搜索失败",
      );
      setHits(data.items || []);
    } catch {
      // runWithToast 已经弹了 toast；这里只清空结果 + 留行内错误
      setHits([]);
      setInlineError("搜索失败，请稍后重试");
    } finally {
      setSearching(false);
      setSearched(true);
    }
  };

  const handlePick = async (hit: MetadataHit) => {
    setFetchingId(hit.song_id);
    setInlineError("");
    try {
      const detail = await runWithToast(
        () => apiRequest<MetadataSongDetail>("/api/metadata/song", {
          method: "POST",
          body: { song_id: hit.song_id, preferred_provider: hit.source },
        }),
        "获取歌曲详情失败",
      );
      onPick(detail);
      onClose();
    } catch {
      setInlineError(`「${hit.title}」详情获取失败，可重试或换一条`);
    } finally {
      setFetchingId(null);
    }
  };

  const trimmedKeyword = (keyword || "").trim();

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent
        className="sm:max-w-[540px] max-h-[80vh] overflow-hidden flex flex-col"
        data-testid="metadata-search-dialog"
      >
        <DialogHeader>
          <DialogTitle>在线补全 · {trimmedKeyword || "（未输入关键词）"}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto min-h-0 space-y-2">
          {!trimmedKeyword && (
            <p className="text-sm text-muted-foreground py-8 text-center" data-testid="empty-keyword">
              请先在歌名输入框填入要搜索的关键词
            </p>
          )}

          {trimmedKeyword && searching && (
            <p className="text-sm text-muted-foreground py-6 text-center" data-testid="searching">
              正在搜索「{trimmedKeyword}」…
            </p>
          )}

          {trimmedKeyword && searched && !searching && hits.length === 0 && !inlineError && (
            <p className="text-sm text-muted-foreground py-8 text-center" data-testid="no-results">
              未找到匹配「{trimmedKeyword}」的歌曲
            </p>
          )}

          {inlineError && (
            <p className="text-sm text-destructive py-2" role="alert" data-testid="inline-error">
              {inlineError}
            </p>
          )}

          {hits.length > 0 && (
            <ul className="space-y-1.5" data-testid="hit-list">
              {hits.map(hit => {
                const isFetching = fetchingId === hit.song_id;
                return (
                  <li key={`${hit.source}:${hit.song_id}`}>
                    <button
                      type="button"
                      onClick={() => handlePick(hit)}
                      disabled={!!fetchingId}
                      data-testid="hit-item"
                      data-song-id={hit.song_id}
                      className="w-full text-left px-3 py-2 rounded-md hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      <div className="flex items-baseline gap-2">
                        <span className="font-medium text-sm truncate flex-1">
                          {hit.title}
                        </span>
                        <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                          {formatDuration(hit.duration_ms)}
                        </span>
                      </div>
                      <div className="flex items-baseline gap-2 mt-0.5 text-xs text-muted-foreground">
                        <span className="truncate flex-1">
                          {hit.artist}
                          {hit.album ? ` · ${hit.album}` : ""}
                        </span>
                        {isFetching && (
                          <span className="text-[10px] text-primary shrink-0" data-testid="fetching">
                            获取详情…
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => void runSearch(trimmedKeyword)}
            disabled={searching || !trimmedKeyword}
            data-testid="refresh-button"
          >
            重新搜索
          </Button>
          <Button type="button" variant="ghost" onClick={onClose} data-testid="close-button">
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
