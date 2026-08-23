/// P1-A2: 5 动作 React hook 集合 — LibraryView 多选后批量动作入口
///
/// 5 个动作（顺序对应 SongActionBar 的 5 个按钮）：
///   1. addToCurrentPoster  — 加入当前海报（依赖 App 提供的 onAddToCurrentPoster 回调）
///   2. addToTonightSession — 加入今晚歌单（依赖 App 提供的 activeSessionId + onEnqueue 回调）
///   3. addToLearningPlan   — 加入学习计划（POST /api/practice/log 占位打卡，源 library-add-to-plan）
///   4. play                — 切 PlayerContext.setCurrent(firstId, "browse")
///   5. editSong            — 触发 onEditSong 回调（LibraryView 决定打开 SongEditDialog）
///
/// 设计原则：
///   - 失败 → toast.error + 不抛错（任务硬约束）
///   - 任何 toast 通过 useToast() 内部完成，caller 不必再包 try/catch
///   - titles: string[] 输入（LibraryView 用 selectedTitles），内部按 title 反查 songsData.songs 拿 id
///   - songsData: SongsData | null 输入
///   - 0 后端改动：复用现存端点（practice/log + live-sessions/{id}/queue）
///
/// 为什么不放在 store：LibraryView 不持有 poster store（App 持有一个 usePosterStore 实例
/// 给 WorkspacePosterBridge），跨视图共享 store 需要 App 注入。本 hook 不引入新 store，
/// 只暴露 5 个函数 + App 提供的 callback（onAddToCurrentPoster / onEnqueue / onEditSong）。
import { useCallback } from "react";
import { apiRequest } from "../api/client";
import { useToast } from "../components/Toast";
import { usePlayer } from "../player/PlayerContext";
import type { SongsData } from "../types";

/** 单个 action 的入参：title 列表 + 当前曲库快照（反查 song_id 用）。 */
export interface SongActionInput {
  titles: string[];
  songsData: SongsData | null;
}

export interface UseSongActionsOptions {
  /**
   * 「加入当前海报」时调：把 song_ids 追加到 App 那个 poster store 的 selected_song_ids。
   * 不传 → action 退化为只 toast 提示。
   * LibraryView 通过 prop 拿到本回调。
   */
  onAddToCurrentPoster?: (songIds: string[]) => void;
  /**
   * 当前活跃的直播 session id（来自 App 端的 live-sessions 列表）。
   * null → 按钮 disabled（SongActionBar 用 hasActiveSession prop 控制）。
   * 在「加入今晚歌单」时用：把 song_id 入队到这场直播。
   */
  activeSessionId: string | null;
  /**
   * 「加入今晚歌单」时调：把 song_id 入队到 App 提供的 sessionId 那场直播。
   * 不传 → action 退化为只 toast 提示「未启用」。
   */
  onEnqueue?: (sessionId: string, songId: string, title: string) => Promise<void> | void;
  /**
   * 「编辑」时调：把 title 交给 LibraryView 打开 SongEditDialog。
   * 必传（无默认行为）。
   */
  onEditSong?: (title: string) => void;
}

export interface UseSongActions {
  addToCurrentPoster: (input: SongActionInput) => Promise<void>;
  addToTonightSession: (input: SongActionInput) => Promise<void>;
  addToLearningPlan: (input: SongActionInput) => Promise<void>;
  play: (input: SongActionInput) => Promise<void>;
  editSong: (input: SongActionInput) => void;
}

/** titles → 唯一 song_id 列表（按 songsData.songs.find 反查；找不到的 title 跳过 + 计入 skipped）。 */
function resolveSongIds(
  titles: string[], songsData: SongsData | null,
): { ids: string[]; skipped: string[] } {
  const ids: string[] = [];
  const skipped: string[] = [];
  if (!songsData) return { ids, skipped: titles };
  for (const title of titles) {
    const song = songsData.songs.find(s => s.title === title);
    if (song) ids.push(song.id);
    else skipped.push(title);
  }
  return { ids, skipped };
}

/**
 * P1-A2: 5 动作 hook。LibraryView 在 select 模式下用。
 *
 * - addToCurrentPoster / addToTonightSession：依赖 App 提供的 callback；缺失时退化为
 *   toast.info 提示「需要先在 App 接线」，不抛错。
 * - addToLearningPlan：调 POST /api/practice/log minutes=1 + source="library-add-to-plan"；
 *   失败 → toast.error + 静默。
 * - play：调 usePlayer().setCurrent(firstId, "browse")；PlayerMode 没有 "play" 字面值，
 *   用 "browse"（LibraryView 弹唱入口 = browse 模式，由 MiniPlayer 决定何时跳 PlayView）。
 * - editSong：只对单选生效；多选时 toast.warn 提示"编辑仅支持单选"。
 */
export function useSongActions(options: UseSongActionsOptions): UseSongActions {
  const { onAddToCurrentPoster, onEnqueue, onEditSong, activeSessionId } = options;
  const toast = useToast();
  const player = usePlayer();

  /* ---------- 1. 加入当前海报 ---------- */
  const addToCurrentPoster = useCallback(async ({ titles, songsData }: SongActionInput) => {
    if (titles.length === 0) return;
    const { ids, skipped } = resolveSongIds(titles, songsData);
    if (ids.length === 0) {
      toast.warn("未能解析选中歌曲的 ID");
      return;
    }
    if (!onAddToCurrentPoster) {
      toast.info("加入当前海报：未启用（App 接线缺失）");
      return;
    }
    try {
      onAddToCurrentPoster(ids);
      const skippedMsg = skipped.length > 0 ? `（跳过 ${skipped.length} 首未识别）` : "";
      toast.show({
        message: `已加入当前海报：${ids.length} 首${skippedMsg}`,
        durationMs: 3000,
      });
    } catch (err) {
      // callback 内 sync throw 的兜底（正常 callback 不应抛）
      toast.error(`加入当前海报失败：${err instanceof Error ? err.message : String(err)}`);
    }
  }, [onAddToCurrentPoster, toast]);

  /* ---------- 2. 加入今晚歌单 ---------- */
  const addToTonightSession = useCallback(async ({ titles, songsData }: SongActionInput) => {
    if (titles.length === 0) return;
    if (!activeSessionId) {
      toast.info("今晚没有活跃直播场次，先到「直播」标签开一场");
      return;
    }
    if (!onEnqueue) {
      toast.info("加入今晚歌单：未启用（App 接线缺失）");
      return;
    }
    const { ids, skipped } = resolveSongIds(titles, songsData);
    if (ids.length === 0) {
      toast.warn("未能解析选中歌曲的 ID");
      return;
    }
    let succeeded = 0;
    const failed: string[] = [];
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const title = titles[i] ?? id;
      try {
        await onEnqueue(activeSessionId, id, title);
        succeeded++;
      } catch (err) {
        failed.push(`${title}：${err instanceof Error ? err.message : String(err)}`);
      }
    }
    if (succeeded > 0) {
      const skippedMsg = skipped.length > 0 ? `（跳过 ${skipped.length} 首未识别）` : "";
      const failedMsg = failed.length > 0 ? `，${failed.length} 首失败` : "";
      toast.show({
        message: `已加入今晚歌单：${succeeded} 首${skippedMsg}${failedMsg}`,
        durationMs: failed.length > 0 ? 5000 : 3000,
      });
    } else {
      toast.error(failed[0] ?? "加入今晚歌单失败");
    }
  }, [onEnqueue, activeSessionId, toast]);

  /* ---------- 3. 加入学习计划 ---------- */
  const addToLearningPlan = useCallback(async ({ titles, songsData }: SongActionInput) => {
    if (titles.length === 0) return;
    const { ids, skipped } = resolveSongIds(titles, songsData);
    if (ids.length === 0) {
      toast.warn("未能解析选中歌曲的 ID");
      return;
    }
    // 后端 PracticeLog 验证：minutes >= 1；source 标 library-add-to-plan 与正常练习打卡区分。
    // P1-A4 学习计划真持久化前，这是合规的"加入计划"信号——事件可被 stats 拉到。
    let succeeded = 0;
    const failed: string[] = [];
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const title = titles[i] ?? id;
      try {
        await apiRequest<{ ok?: boolean }>("/api/practice/log", {
          method: "POST",
          body: {
            song_id: id,
            title_snapshot: title,
            minutes: 1,
            self_rating: 0,
            note: "加入学习计划",
            source: "library-add-to-plan",
          },
        });
        succeeded++;
      } catch (err) {
        failed.push(`${title}：${err instanceof Error ? err.message : String(err)}`);
      }
    }
    if (succeeded > 0) {
      const skippedMsg = skipped.length > 0 ? `（跳过 ${skipped.length} 首未识别）` : "";
      const failedMsg = failed.length > 0 ? `，${failed.length} 首失败` : "";
      toast.show({
        message: `已加入学习计划：${succeeded} 首${skippedMsg}${failedMsg}`,
        durationMs: failed.length > 0 ? 5000 : 3000,
      });
    } else {
      toast.error(failed[0] ?? "加入学习计划失败");
    }
  }, [toast]);

  /* ---------- 4. 弹唱（仅取首首设置 PlayerContext） ---------- */
  const play = useCallback(async ({ titles, songsData }: SongActionInput) => {
    if (titles.length === 0) return;
    const { ids } = resolveSongIds(titles, songsData);
    if (ids.length === 0) {
      toast.warn("未能解析选中歌曲的 ID");
      return;
    }
    const firstId = ids[0];
    // PlayerMode = "live" | "practice" | "browse"；library 弹唱选 browse（与 CommandPalette / 单曲 ▶ 一致）。
    player.setCurrent(firstId, "browse");
    if (titles.length > 1) {
      toast.show({
        message: `已选「${titles[0]}」开始弹唱（${titles.length - 1} 首待切歌）`,
        durationMs: 3000,
      });
    }
    // 单选时不弹 toast（无声切换；MiniPlayer 自动出现）
  }, [player, toast]);

  /* ---------- 5. 编辑（仅单选生效） ---------- */
  const editSong = useCallback(({ titles }: SongActionInput) => {
    if (titles.length === 0) return;
    if (titles.length > 1) {
      toast.warn("编辑仅支持单选：先清空其他选择");
      return;
    }
    if (!onEditSong) {
      toast.info("编辑：未启用（App 接线缺失）");
      return;
    }
    onEditSong(titles[0]);
  }, [onEditSong, toast]);

  return {
    addToCurrentPoster,
    addToTonightSession,
    addToLearningPlan,
    play,
    editSong,
  };
}
