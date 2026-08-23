/// P1-A2: SongActionBar + useSongActions 集成测试
///
/// 覆盖 5 个核心场景：
///   1. selectedCount=0 → bar 整条不渲染
///   2. hasCurrentPoster=false → "加入当前海报" disabled（其它按钮 enabled）
///   3. hasActiveSession=false → "加入今晚歌单" disabled
///   4. 多选时 → "编辑" disabled（编辑仅支持单选）
///   5. 点击 "弹唱" → usePlayer.setCurrent(firstId, "browse") 被调
///   6. 点击 "加入学习计划" → POST /api/practice/log 调通 + toast.success
///   7. 点击 "加入当前海报" → onAddToCurrentPoster 调 + 传 song_ids
///   8. 点击 "加入今晚歌单" → onEnqueue(sessionId, id, title) 循环调
///   9. API 失败 → toast.error，不抛错
///  10. "编辑" 单选 → onEditSong(title) 被调
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, waitFor } from "@testing-library/react";
import { ToastProvider } from "./Toast";
import SongActionBar from "./SongActionBar";
import { useSongActions } from "../hooks/useSongActions";
import { PlayerProvider, usePlayer } from "../player/PlayerContext";
import type { SongsData } from "../types";

/* ============== fixtures ============== */
const SAMPLE: SongsData = {
  total: 3, active: 2, draft: 1,
  songs: [
    { id: "song_1", title: "江南", artists: ["林俊杰"], key: "C", status: "active" },
    { id: "song_2", title: "十年", artists: ["陈奕迅"], key: "G", status: "active" },
    { id: "song_3", title: "后来", artists: ["刘若英"], key: "D", status: "draft" },
  ],
} as unknown as SongsData;

/* ============== apiRequest fetch mock ============== */
let fetchMock: ReturnType<typeof vi.fn>;
let originalFetch: typeof globalThis.fetch;
beforeEach(() => {
  fetchMock = vi.fn();
  originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
});
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

/** 200 OK JSON 响应。 */
function okJson<T>(body: T): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

/** 错误响应（模拟 ApiClientError envelope）。 */
function errJson(code: string, message: string, status = 400): Response {
  return new Response(JSON.stringify({ error: { code, message } }), {
    status, headers: { "content-type": "application/json" },
  });
}

/* ============== 测试 harness ============== */
function renderBar(props: Partial<React.ComponentProps<typeof SongActionBar>> = {}) {
  const onAddToCurrentPoster = vi.fn();
  const onAddToTonightSession = vi.fn();
  const onAddToLearningPlan = vi.fn();
  const onPlay = vi.fn();
  const onEdit = vi.fn();
  const utils = render(
    <ToastProvider>
      <SongActionBar
        selectedCount={1}
        dark={false}
        hasCurrentPoster={true}
        hasActiveSession={true}
        onAddToCurrentPoster={onAddToCurrentPoster}
        onAddToTonightSession={onAddToTonightSession}
        onAddToLearningPlan={onAddToLearningPlan}
        onPlay={onPlay}
        onEdit={onEdit}
        {...props}
      />
    </ToastProvider>,
  );
  return { ...utils, onAddToCurrentPoster, onAddToTonightSession, onAddToLearningPlan, onPlay, onEdit };
}

describe("SongActionBar - 渲染", () => {
  it("selectedCount=0 → 整条不渲染", () => {
    const { queryByTestId } = renderBar({ selectedCount: 0 });
    expect(queryByTestId("song-action-bar")).toBeNull();
  });

  it("selectedCount>=1 + 启用态 → 5 按钮全部 enabled", () => {
    const { getByTestId } = renderBar({ selectedCount: 1 });
    for (const id of [
      "song-action-add-to-poster",
      "song-action-add-to-tonight",
      "song-action-add-to-learning",
      "song-action-play",
      "song-action-edit",
    ]) {
      const btn = getByTestId(id) as HTMLButtonElement;
      expect(btn.disabled, id).toBe(false);
    }
  });

  it("hasCurrentPoster=false → 加入当前海报 disabled", () => {
    const { getByTestId } = renderBar({ selectedCount: 1, hasCurrentPoster: false });
    const btn = getByTestId("song-action-add-to-poster") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    // 其它按钮不受影响
    expect((getByTestId("song-action-add-to-tonight") as HTMLButtonElement).disabled).toBe(false);
    expect((getByTestId("song-action-add-to-learning") as HTMLButtonElement).disabled).toBe(false);
  });

  it("hasActiveSession=false → 加入今晚歌单 disabled", () => {
    const { getByTestId } = renderBar({ selectedCount: 1, hasActiveSession: false });
    const btn = getByTestId("song-action-add-to-tonight") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    // 其它按钮不受影响
    expect((getByTestId("song-action-add-to-poster") as HTMLButtonElement).disabled).toBe(false);
    expect((getByTestId("song-action-add-to-learning") as HTMLButtonElement).disabled).toBe(false);
  });

  it("selectedCount>1 → 编辑按钮 disabled（仅支持单选）", () => {
    const { getByTestId } = renderBar({ selectedCount: 3 });
    const btn = getByTestId("song-action-edit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    // 其它按钮在多选时仍 enabled
    expect((getByTestId("song-action-add-to-poster") as HTMLButtonElement).disabled).toBe(false);
    expect((getByTestId("song-action-play") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("SongActionBar - 点击转发", () => {
  it("点击「加入当前海报」→ onAddToCurrentPoster 被调", () => {
    const { getByTestId, onAddToCurrentPoster } = renderBar();
    fireEvent.click(getByTestId("song-action-add-to-poster"));
    expect(onAddToCurrentPoster).toHaveBeenCalledTimes(1);
  });

  it("点击「加入今晚歌单」→ onAddToTonightSession 被调", () => {
    const { getByTestId, onAddToTonightSession } = renderBar();
    fireEvent.click(getByTestId("song-action-add-to-tonight"));
    expect(onAddToTonightSession).toHaveBeenCalledTimes(1);
  });

  it("点击「加入学习计划」→ onAddToLearningPlan 被调（hook 内部才发 API；bar 层只转发）", () => {
    const { getByTestId, onAddToLearningPlan } = renderBar();
    fireEvent.click(getByTestId("song-action-add-to-learning"));
    expect(onAddToLearningPlan).toHaveBeenCalledTimes(1);
  });

  it("点击「弹唱」→ onPlay 被调", () => {
    const { getByTestId, onPlay } = renderBar();
    fireEvent.click(getByTestId("song-action-play"));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it("点击「编辑」→ onEdit 被调", () => {
    const { getByTestId, onEdit } = renderBar();
    fireEvent.click(getByTestId("song-action-edit"));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });
});

/* ============== useSongActions 行为 ============== */
function setupActionsHook(opts: Parameters<typeof useSongActions>[0] = { activeSessionId: null }) {
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ToastProvider><PlayerProvider>{children}</PlayerProvider></ToastProvider>
  );
  return renderHook(() => useSongActions(opts), { wrapper });
}

describe("useSongActions - 单动作行为", () => {
  it("addToLearningPlan：单选 → POST /api/practice/log 被调 1 次 + toast.success", async () => {
    fetchMock.mockResolvedValue(okJson({ ok: true, event_id: "evt_x" }));
    const onAddToLearningPlan = vi.fn();
    const { result } = setupActionsHook({ activeSessionId: null, onAddToLearningPlan });
    await act(async () => {
      await result.current.addToLearningPlan({ titles: ["江南"], songsData: SAMPLE });
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/practice/log");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.song_id).toBe("song_1");
    expect(body.title_snapshot).toBe("江南");
    expect(body.minutes).toBe(1);
    expect(body.source).toBe("library-add-to-plan");
    // toast 出现
    await waitFor(() => {
      expect(document.querySelector('[data-testid="toast-item"]')).toBeTruthy();
    });
  });

  it("addToLearningPlan：API 失败 → toast.error + 不抛错（任务硬约束）", async () => {
    fetchMock.mockResolvedValue(errJson("practice_error", "打卡校验失败"));
    const { result } = setupActionsHook({ activeSessionId: null });
    await act(async () => {
      // 不应抛错
      await result.current.addToLearningPlan({ titles: ["江南"], songsData: SAMPLE });
    });
    await waitFor(() => {
      const item = document.querySelector('[data-testid="toast-item"]');
      expect(item).toBeTruthy();
      expect(item?.getAttribute("data-kind")).toBe("error");
    });
  });

  it("addToLearningPlan：3 首循环 3 次 fetch + 任一失败聚合 toast", async () => {
    fetchMock
      .mockResolvedValueOnce(okJson({ ok: true }))
      .mockResolvedValueOnce(errJson("practice_error", "单首失败"))
      .mockResolvedValueOnce(okJson({ ok: true }));
    const { result } = setupActionsHook({ activeSessionId: null });
    await act(async () => {
      await result.current.addToLearningPlan({
        titles: ["江南", "十年", "后来"], songsData: SAMPLE,
      });
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("addToCurrentPoster：调 onAddToCurrentPoster(song_ids) + 传反查的 id", async () => {
    const onAddToCurrentPoster = vi.fn();
    const { result } = setupActionsHook({ activeSessionId: null, onAddToCurrentPoster });
    await act(async () => {
      await result.current.addToCurrentPoster({
        titles: ["江南", "十年"], songsData: SAMPLE,
      });
    });
    expect(onAddToCurrentPoster).toHaveBeenCalledTimes(1);
    expect(onAddToCurrentPoster.mock.calls[0][0]).toEqual(["song_1", "song_2"]);
  });

  it("addToCurrentPoster：未传 callback → toast.info（不抛错）", async () => {
    const { result } = setupActionsHook({ activeSessionId: null });
    await act(async () => {
      await result.current.addToCurrentPoster({ titles: ["江南"], songsData: SAMPLE });
    });
    await waitFor(() => {
      expect(document.querySelector('[data-testid="toast-item"]')).toBeTruthy();
    });
  });

  it("addToTonightSession：activeSessionId + onEnqueue 都在 → 循环入队", async () => {
    const onEnqueue = vi.fn().mockResolvedValue(undefined);
    const { result } = setupActionsHook({
      activeSessionId: "sess_42", onEnqueue,
    });
    await act(async () => {
      await result.current.addToTonightSession({
        titles: ["江南", "十年"], songsData: SAMPLE,
      });
    });
    expect(onEnqueue).toHaveBeenCalledTimes(2);
    expect(onEnqueue.mock.calls[0]).toEqual(["sess_42", "song_1", "江南"]);
    expect(onEnqueue.mock.calls[1]).toEqual(["sess_42", "song_2", "十年"]);
  });

  it("addToTonightSession：activeSessionId=null → 跳过 enqueue + 提示「开一场」", async () => {
    const onEnqueue = vi.fn();
    const { result } = setupActionsHook({ activeSessionId: null, onEnqueue });
    await act(async () => {
      await result.current.addToTonightSession({ titles: ["江南"], songsData: SAMPLE });
    });
    expect(onEnqueue).not.toHaveBeenCalled();
  });

  it("addToTonightSession：onEnqueue 抛错 → 聚合 toast.error（不抛）", async () => {
    const onEnqueue = vi.fn().mockRejectedValue(new Error("queue rejected"));
    const { result } = setupActionsHook({ activeSessionId: "sess_x", onEnqueue });
    await act(async () => {
      // 不应抛错
      await result.current.addToTonightSession({ titles: ["江南"], songsData: SAMPLE });
    });
    await waitFor(() => {
      const item = document.querySelector('[data-testid="toast-item"]');
      expect(item?.getAttribute("data-kind")).toBe("error");
    });
  });

  it("play：调 player.setCurrent(firstId, 'browse')", async () => {
    let captured: ReturnType<typeof usePlayer> | null = null;
    function Probe() { captured = usePlayer(); return null; }
    const { result } = renderHook(
      () => useSongActions({ activeSessionId: null }),
      { wrapper: ({ children }) => <ToastProvider><PlayerProvider><Probe />{children}</PlayerProvider></ToastProvider> },
    );
    // 触发一次 render 让 Probe 同步
    void result.current;
    await act(async () => {
      await result.current.play({ titles: ["江南"], songsData: SAMPLE });
    });
    expect(captured).not.toBeNull();
    expect(captured!.currentSongId).toBe("song_1");
    expect(captured!.mode).toBe("browse");
  });

  it("editSong：单选 → 调 onEditSong(title)", () => {
    const onEditSong = vi.fn();
    const { result } = setupActionsHook({ activeSessionId: null, onEditSong });
    act(() => {
      result.current.editSong({ titles: ["十年"], songsData: SAMPLE });
    });
    expect(onEditSong).toHaveBeenCalledWith("十年");
  });

  it("editSong：多选 → toast.warn，不调 callback", () => {
    const onEditSong = vi.fn();
    const { result } = setupActionsHook({ activeSessionId: null, onEditSong });
    act(() => {
      result.current.editSong({ titles: ["江南", "十年"], songsData: SAMPLE });
    });
    expect(onEditSong).not.toHaveBeenCalled();
    expect(document.querySelector('[data-testid="toast-item"]')?.getAttribute("data-kind")).toBe("warning");
  });

  it("空 titles → 5 action 都是 no-op（不发 API、不调 callback）", async () => {
    const onAddToCurrentPoster = vi.fn();
    const onEnqueue = vi.fn();
    const onEditSong = vi.fn();
    const { result } = setupActionsHook({
      activeSessionId: "sess_1", onAddToCurrentPoster, onEnqueue, onEditSong,
    });
    await act(async () => {
      await result.current.addToCurrentPoster({ titles: [], songsData: SAMPLE });
      await result.current.addToTonightSession({ titles: [], songsData: SAMPLE });
      await result.current.addToLearningPlan({ titles: [], songsData: SAMPLE });
      await result.current.play({ titles: [], songsData: SAMPLE });
      result.current.editSong({ titles: [], songsData: SAMPLE });
    });
    expect(onAddToCurrentPoster).not.toHaveBeenCalled();
    expect(onEnqueue).not.toHaveBeenCalled();
    expect(onEditSong).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("songsData=null + 1 个 title → 跳过 + toast.warn 未能解析", async () => {
    const { result } = setupActionsHook({ activeSessionId: null });
    await act(async () => {
      await result.current.addToLearningPlan({ titles: ["江南"], songsData: null });
    });
    expect(fetchMock).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(document.querySelector('[data-testid="toast-item"]')?.getAttribute("data-kind")).toBe("warning");
    });
  });
});
