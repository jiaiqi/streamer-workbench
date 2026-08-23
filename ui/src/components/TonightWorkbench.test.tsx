/// P1-A1 TonightWorkbench 测试（5 个 spec + 1 个回归）。
///
/// 覆盖：
/// 1. 空态（无活跃 session）：显示「开始直播」按钮 + 「暂无进行中场次」文案
/// 2. active 状态：拉 /api/live-sessions 返回 1 个 active session + 3 条 queue；
///    显示状态徽标「进行中」+ 队列列表 + ▶ 弹唱按钮
/// 3. closed 状态 + 复盘按钮可见：mock 1 个 closed session；
///    「生成复盘海报」按钮可见且 onGenerateRecap 被调
/// 4. 准备检查 - 缺曲谱：mock 1 首歌 tabs="" lyrics_plain="" audio_vocal_path=null key="C"；
///    显示「1/2 项就绪」+ 缺失清单
/// 5. Top 3 一键创建海报：mock /api/stats/top-songs 返回 3 项；
///    点「用 Top 3 创建海报」按钮 → onCreatePosterFromTop 被调且参数是 3 个 song id
///
/// 设计：复用 @testing-library/react 的 render / screen / fireEvent / waitFor；
///      mock /api/client.apiRequest（保留 ApiClientError 等其他 export 以免
///      toRequestFailure 内部 instanceof 检查崩溃）；
///      用 mockRoute(url pattern → value) 派发 mock 数据，避免 useEffect 顺序
///      不确定导致 mockResolvedValueOnce 串号。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const apiRequest = vi.fn();
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => apiRequest(...args),
  };
});

// —— 通用 mock 路由器：按 URL 匹配 + 每次调用取下一个匹配值（queue 模式） ——
type Rule = [matcher: (url: string) => boolean, values: unknown[]];
function mockRoute(api: ReturnType<typeof vi.fn>, rules: Rule[]) {
  // 每次匹配按 URL 走第 N 次匹配的 queue
  const counters = new Map<Rule, number>();
  api.mockImplementation((url: string) => {
    for (const rule of rules) {
      const [matcher, values] = rule;
      if (!matcher(url)) continue;
      const idx = counters.get(rule) ?? 0;
      counters.set(rule, idx + 1);
      const val = values[idx];
      return Promise.resolve(val);
    }
    return Promise.resolve(undefined);
  });
}

// 常用 matcher
const m = {
  sessionsList: (url: string) => url.endsWith("/api/live-sessions"),
  sessionDetail: (id: string) => (url: string) => url.includes(`/api/live-sessions/${id}`),
  songsList: (url: string) => url.includes("/api/songs/list"),
  topSongs: (url: string) => url.includes("/api/stats/top-songs"),
};

// —— 辅助：构造可识别的 mock response ——
const ACTIVE_SESSION_SUMMARY = {
  id: "sess_active_1", state: "active", title: "今晚 8 点直播",
  rule_version: "rv1", started_at: "2026-08-23T20:00:00Z", closed_at: null, queue_size: 3,
};
const CLOSED_SESSION_SUMMARY = {
  id: "sess_closed_1", state: "closed", title: "昨晚直播",
  rule_version: "rv1", started_at: "2026-08-22T20:00:00Z", closed_at: "2026-08-22T23:00:00Z", queue_size: 5,
};
const ACTIVE_DETAIL = {
  id: "sess_active_1", state: "active", title: "今晚 8 点直播", rule_version: "rv1",
  started_at: "2026-08-23T20:00:00Z", closed_at: null, poster_id: null, notes: "",
  queue: [
    { request_id: "q1", song_id: "song_a", position: 1, state: "current",
      is_bumped: false, requester_name: "小明", entitlement_kind: "manual",
      inserted_at: "2026-08-23T20:01:00Z" },
    { request_id: "q2", song_id: "song_b", position: 2, state: "queued",
      is_bumped: false, requester_name: "小红", entitlement_kind: "",
      inserted_at: "2026-08-23T20:02:00Z" },
    { request_id: "q3", song_id: "song_c", position: 3, state: "sung",
      is_bumped: false, requester_name: "小刚", entitlement_kind: "",
      inserted_at: "2026-08-23T20:03:00Z" },
  ],
  performances: [],
};
const TITLES_LIST = {
  songs: [
    { id: "song_a", title: "江南", artists: ["林俊杰"] },
    { id: "song_b", title: "十年", artists: ["陈奕迅"] },
    { id: "song_c", title: "夜曲", artists: ["周杰伦"] },
  ],
  total: 3, active: 3, draft: 0,
};
const SONG_FOR_READINESS = {
  id: "song_bare", title: "无伴奏", artists: [],
  tabs: "", lyrics_plain: "", lyrics_lrc: "",
  audio_vocal_path: null, key: "C",
};
const SONG_FULLY_READY = {
  id: "song_ready", title: "完整版", artists: [],
  tabs: "chordpro body", lyrics_plain: "歌词", lyrics_lrc: "[00:00.00]歌词",
  audio_vocal_path: "audio/song_ready/vocal.mp3", key: "C",
};
const READINESS_SONGS = { songs: [SONG_FOR_READINESS, SONG_FULLY_READY], total: 2, active: 2, draft: 0 };
const FAKE_TOP = {
  metric: "request", note: "",
  items: [
    { song_id: "s1", title: "晴天", artist: "周杰伦", count: 12, minutes: 0 },
    { song_id: "s2", title: "十年", artist: "陈奕迅", count: 8, minutes: 0 },
    { song_id: "s3", title: "倔强", artist: "五月天", count: 5, minutes: 0 },
  ],
};

beforeEach(() => {
  apiRequest.mockReset();
  if (typeof localStorage !== "undefined") localStorage.clear();
  if (typeof sessionStorage !== "undefined") sessionStorage.clear();
});

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("TonightWorkbench (P1-A1)", () => {
  it("空态：没有活跃 session 时显示「开始直播」按钮 + 「暂无进行中场次」", async () => {
    mockRoute(apiRequest, [
      [m.sessionsList, [[]]],
      [m.topSongs, [FAKE_TOP]],
    ]);
    const onOpenLiveView = vi.fn();
    render(
      <TonightWorkbenchImport
        dark={false}
        onPlaySong={vi.fn()}
        onOpenLiveView={onOpenLiveView}
        onCreatePosterFromTop={vi.fn()}
        onSwitchToStats={vi.fn()}
      />,
    );
    // 「开始直播」按钮
    expect(await screen.findByTestId("tw-action-start-live")).toBeTruthy();
    // 「暂无进行中场次」标题文案
    expect(screen.getByText("暂无进行中场次")).toBeTruthy();
    // 「还没有开始一场直播」空态文案（C 区）
    expect(screen.getByTestId("tw-queue-empty")).toBeTruthy();
    // 状态徽标 = none
    const badge = screen.getByTestId("tw-status-badge");
    expect(badge.getAttribute("data-session-state")).toBe("none");
  });

  it("active 状态：状态徽标「进行中」+ 队列列表 + ▶ 弹唱按钮触发 onPlaySong", async () => {
    mockRoute(apiRequest, [
      [m.sessionsList, [[ACTIVE_SESSION_SUMMARY]]],
      [m.sessionDetail("sess_active_1"), [ACTIVE_DETAIL, ACTIVE_DETAIL]], // C区 + D区 detail 各一次
      [m.songsList, [TITLES_LIST, READINESS_SONGS]],                       // C区 titles, D区 readiness
      [m.topSongs, [FAKE_TOP]],
    ]);

    const onPlaySong = vi.fn();
    render(
      <TonightWorkbenchImport
        dark={false}
        onPlaySong={onPlaySong}
        onOpenLiveView={vi.fn()}
        onCreatePosterFromTop={vi.fn()}
        onSwitchToStats={vi.fn()}
        onOpenQuickView={vi.fn()}
      />,
    );
    // 状态徽标 → active
    await waitFor(() => {
      expect(screen.getByTestId("tw-status-badge").getAttribute("data-session-state")).toBe("active");
    });
    expect(screen.getByTestId("tw-status-badge").textContent).toContain("进行中");
    // active 时显示「打开速查」+「完整队列」按钮
    expect(screen.getByTestId("tw-action-open-quickview")).toBeTruthy();
    expect(screen.getByTestId("tw-action-open-full-queue")).toBeTruthy();
    // 队列列表（current + queued 出现；sung 被过滤）
    await waitFor(() => {
      expect(screen.getAllByTestId("tw-queue-item").length).toBe(2);
    });
    // 歌名加载（C区 queue 中出现「江南」「十年」）
    await waitFor(() => {
      expect(screen.getByText("江南")).toBeTruthy();
    });
    // 「十年」既在 C区 queue 也在 E区 top-3 中；用 getAllByText 检查 ≥1
    expect(screen.getAllByText("十年").length).toBeGreaterThanOrEqual(1);
    // 点 ▶ 弹唱按钮 → onPlaySong 被调
    const playBtns = document.querySelectorAll('[data-testid="tw-queue-play"]');
    expect(playBtns.length).toBe(2);
    fireEvent.click(playBtns[0]);
    expect(onPlaySong).toHaveBeenCalledWith("song_a", {
      sessionId: "sess_active_1",
      requestId: "q1",
      requesterName: "小明",
    });
  });

  it("closed 状态：「生成复盘海报」按钮可见且 onGenerateRecap 被调", async () => {
    mockRoute(apiRequest, [
      [m.sessionsList, [[CLOSED_SESSION_SUMMARY]]],
      [m.topSongs, [FAKE_TOP]],
    ]);
    const onGenerateRecap = vi.fn();
    render(
      <TonightWorkbenchImport
        dark={false}
        onPlaySong={vi.fn()}
        onOpenLiveView={vi.fn()}
        onCreatePosterFromTop={vi.fn()}
        onSwitchToStats={vi.fn()}
        onGenerateRecap={onGenerateRecap}
        onGenerateLearningReport={vi.fn()}
      />,
    );
    // 状态徽标 → closed
    await waitFor(() => {
      expect(screen.getByTestId("tw-status-badge").getAttribute("data-session-state")).toBe("closed");
    });
    // 复盘按钮可见
    const recapBtn = await screen.findByTestId("tw-action-recap");
    expect(recapBtn.textContent).toContain("生成复盘海报");
    // 学习报告按钮可见
    expect(screen.getByTestId("tw-action-learning-report")).toBeTruthy();
    // 点复盘 → onGenerateRecap("sess_closed_1")
    fireEvent.click(recapBtn);
    expect(onGenerateRecap).toHaveBeenCalledTimes(1);
    expect(onGenerateRecap).toHaveBeenCalledWith("sess_closed_1");
  });

  it("准备检查 - 缺曲谱：显示「1/2 项就绪」+ 缺失清单", async () => {
    // 准备一个 queue：含 song_bare（缺 3 项）和 song_ready（全齐）→ readiness=1/2
    const QUEUE_FOR_READINESS = {
      id: "sess_active_1", state: "active", title: "今晚 8 点直播", rule_version: "rv1",
      started_at: "2026-08-23T20:00:00Z", closed_at: null, poster_id: null, notes: "",
      queue: [
        { request_id: "qr1", song_id: "song_bare", position: 1, state: "current",
          is_bumped: false, requester_name: "观众甲", entitlement_kind: "manual",
          inserted_at: "2026-08-23T20:01:00Z" },
        { request_id: "qr2", song_id: "song_ready", position: 2, state: "queued",
          is_bumped: false, requester_name: "观众乙", entitlement_kind: "",
          inserted_at: "2026-08-23T20:02:00Z" },
      ],
      performances: [],
    };
    const ALL_SONGS = {
      songs: [
        SONG_FOR_READINESS,  // id="song_bare", all empty except key
        SONG_FULLY_READY,    // id="song_ready", everything filled
      ],
      total: 2, active: 2, draft: 0,
    };
    mockRoute(apiRequest, [
      [m.sessionsList, [[ACTIVE_SESSION_SUMMARY]]],
      [m.sessionDetail("sess_active_1"), [QUEUE_FOR_READINESS, QUEUE_FOR_READINESS]],
      [m.songsList, [ALL_SONGS, ALL_SONGS]],  // C区 + D区 都拿到完整 ALL_SONGS
      [m.topSongs, [FAKE_TOP]],
    ]);

    render(
      <TonightWorkbenchImport
        dark={false}
        onPlaySong={vi.fn()}
        onOpenLiveView={vi.fn()}
        onCreatePosterFromTop={vi.fn()}
        onSwitchToStats={vi.fn()}
      />,
    );
    // 准备检查摘要（readiness 是 1/2 — song_bare 缺 3 项，song_ready 完整）
    await waitFor(() => {
      const summary = screen.getByTestId("tw-readiness-summary");
      expect(summary.getAttribute("data-ready")).toBe("1");
      expect(summary.getAttribute("data-total")).toBe("2");
      expect(summary.textContent).toMatch(/1\s*\/\s*2/);
    });
    // 缺失清单：song_bare 应出现（key 已就绪，所以只列 3 项）
    await waitFor(() => {
      const items = screen.getAllByTestId("tw-readiness-missing-item");
      const bare = items.find((el) => el.getAttribute("data-song-id") === "song_bare");
      expect(bare).toBeTruthy();
      expect(bare!.textContent).toContain("曲谱");
      expect(bare!.textContent).toContain("歌词");
      expect(bare!.textContent).toContain("音频");
    });
  });

  it("Top 3 一键创建海报：点「用 Top 3 创建海报」触发 onCreatePosterFromTop 传 3 个 song id", async () => {
    mockRoute(apiRequest, [
      [m.sessionsList, [[]]],
      [m.topSongs, [FAKE_TOP]],
    ]);
    const onCreatePosterFromTop = vi.fn().mockResolvedValue(undefined);
    const onSwitchToStats = vi.fn();
    const user = userEvent.setup();
    render(
      <TonightWorkbenchImport
        dark={false}
        onPlaySong={vi.fn()}
        onOpenLiveView={vi.fn()}
        onCreatePosterFromTop={onCreatePosterFromTop}
        onSwitchToStats={onSwitchToStats}
      />,
    );
    // 列表
    await waitFor(() => screen.getByTestId("tw-top-list"));
    expect(screen.getAllByTestId("tw-top-item").length).toBe(3);
    expect(screen.getByText("×12")).toBeTruthy();
    const createBtn = screen.getByTestId("tw-top-create");
    expect(createBtn.textContent).toContain("用 Top 3 创建海报");
    await user.click(createBtn);
    await waitFor(() => {
      expect(onCreatePosterFromTop).toHaveBeenCalledTimes(1);
    });
    expect(onCreatePosterFromTop).toHaveBeenCalledWith(["s1", "s2", "s3"]);
    expect(onSwitchToStats).not.toHaveBeenCalled();
  });

  it("回归：sessions fetch 失败时显示 ErrorBanner（不崩溃）+ E 区仍可加载", async () => {
    // 直接 mockImplementation：sessionsList 失败、其它成功
    apiRequest.mockImplementation((url: string) => {
      if (m.sessionsList(url)) return Promise.reject(new Error("网络炸了"));
      if (m.topSongs(url)) return Promise.resolve(FAKE_TOP);
      return Promise.resolve(undefined);
    });
    render(
      <TonightWorkbenchImport
        dark={false}
        onPlaySong={vi.fn()}
        onOpenLiveView={vi.fn()}
        onCreatePosterFromTop={vi.fn()}
        onSwitchToStats={vi.fn()}
      />,
    );
    // ErrorBanner 应出现（message 通过 useApiError + sessionsReq.run 包装后
    // 落到 ErrorBanner 是 RequestFailure 默认 fallback "请求失败"，但 "重试" 可见即可）
    const banner = await screen.findByTestId("tw-sessions-error");
    expect(banner.textContent).toContain("重试");
    // E 区仍加载成功
    await waitFor(() => screen.getByTestId("tw-top-list"));
    expect(screen.getAllByTestId("tw-top-item").length).toBe(3);
  });
});

// —— 测试模块的内部 import helper：避免 vi.mock 干扰 ——
import TonightWorkbenchImport from "./TonightWorkbench";
