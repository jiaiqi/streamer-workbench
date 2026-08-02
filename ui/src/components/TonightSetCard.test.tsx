/// R9.5 TonightSetCard 测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import TonightSetCard from "./TonightSetCard";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const ACTIVE_SUMMARY = {
  id: "s_active", state: "active", title: "今晚 8 点",
  rule_version: "rv1", started_at: "2026-08-02T20:00:00Z", closed_at: null, queue_size: 3,
};
const ACTIVE_DETAIL = {
  id: "s_active", state: "active", title: "今晚 8 点", rule_version: "rv1",
  started_at: "2026-08-02T20:00:00Z", closed_at: null,
  poster_id: null, notes: "",
  queue: [
    { request_id: "q1", song_id: "song_a", position: 1, state: "current",
      is_bumped: false, requester_name: "小明", entitlement_kind: "manual",
      inserted_at: "2026-08-02T20:01:00Z" },
    { request_id: "q2", song_id: "song_b", position: 2, state: "queued",
      is_bumped: false, requester_name: "小红", entitlement_kind: "",
      inserted_at: "2026-08-02T20:02:00Z" },
    { request_id: "q3", song_id: "song_c", position: 3, state: "sung",
      is_bumped: false, requester_name: "小刚", entitlement_kind: "",
      inserted_at: "2026-08-02T20:03:00Z" },
  ],
  performances: [],
};
const SONGS_LIST = {
  songs: [
    { id: "song_a", title: "江南", artists: ["林俊杰"] },
    { id: "song_b", title: "十年", artists: ["陈奕迅"] },
    { id: "song_c", title: "夜曲", artists: ["周杰伦"] },
  ], total: 3, active: 3, draft: 0,
};

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({}); // 默认
});

afterEach(() => cleanup());

describe("TonightSetCard", () => {
  it("没有活跃 session 时显示「暂无进行中场次」+ 「直播后台 →」按钮", async () => {
    apiRequest.mockResolvedValueOnce([]); // /api/live-sessions
    const onOpenLiveView = vi.fn();
    const { getByTestId, getByText } = render(
      <TonightSetCard dark={false} onPlaySong={vi.fn()} onOpenLiveView={onOpenLiveView} />
    );
    await waitFor(() => {
      expect(getByText("暂无进行中场次")).toBeTruthy();
    });
    fireEvent.click(getByTestId("tonight-set-open"));
    expect(onOpenLiveView).toHaveBeenCalled();
  });

  it("活跃 session 加载后显示 Top N 未唱项（排除 sung）", async () => {
    apiRequest.mockResolvedValueOnce([ACTIVE_SUMMARY]); // sessions list
    apiRequest.mockResolvedValueOnce(ACTIVE_DETAIL);    // session detail
    apiRequest.mockResolvedValueOnce(SONGS_LIST);      // songs list
    const { getByTestId, getByText } = render(
      <TonightSetCard dark={false} onPlaySong={vi.fn()} onOpenLiveView={vi.fn()} />
    );
    await waitFor(() => {
      expect(getByTestId("tonight-set-card").getAttribute("data-session-id")).toBe("s_active");
    });
    await waitFor(() => {
      // current + queued 显示；sung 不显示
      const items = document.querySelectorAll('[data-testid="tonight-set-item"]');
      expect(items.length).toBe(2);
    });
    // 歌名加载
    await waitFor(() => {
      expect(getByText("江南")).toBeTruthy();
      expect(getByText("十年")).toBeTruthy();
    });
  });

  it("点 ▶ 弹唱按钮 → 调 onPlaySong 传入完整 link", async () => {
    apiRequest.mockResolvedValueOnce([ACTIVE_SUMMARY]);
    apiRequest.mockResolvedValueOnce(ACTIVE_DETAIL);
    apiRequest.mockResolvedValueOnce(SONGS_LIST);
    const onPlaySong = vi.fn();
    const { getAllByTestId } = render(
      <TonightSetCard dark={false} onPlaySong={onPlaySong} onOpenLiveView={vi.fn()} />
    );
    await waitFor(() => {
      expect(getAllByTestId("tonight-set-item").length).toBe(2);
    });
    // 第一个 ▶ 按钮
    const playBtns = document.querySelectorAll('[data-testid="tonight-set-play"]');
    fireEvent.click(playBtns[0]);
    expect(onPlaySong).toHaveBeenCalledWith("song_a", {
      sessionId: "s_active",
      requestId: "q1",
      requesterName: "小明",
    });
  });

  it("完整队列按钮存在且可点击", async () => {
    apiRequest.mockResolvedValueOnce([ACTIVE_SUMMARY]);
    apiRequest.mockResolvedValueOnce(ACTIVE_DETAIL);
    apiRequest.mockResolvedValueOnce(SONGS_LIST);
    const onOpenLiveView = vi.fn();
    const { getByTestId } = render(
      <TonightSetCard dark={false} onPlaySong={vi.fn()} onOpenLiveView={onOpenLiveView} />
    );
    await waitFor(() => {
      expect(getByTestId("tonight-set-card").getAttribute("data-session-id")).toBe("s_active");
    });
    expect(getByTestId("tonight-set-open").textContent).toContain("完整队列");
    fireEvent.click(getByTestId("tonight-set-open"));
    expect(onOpenLiveView).toHaveBeenCalled();
  });
});
