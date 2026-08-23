/// M1.5 试听入口测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import LibraryView from "./LibraryView";
import { ToastProvider } from "../components/Toast";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const SONGS_DATA = {
  total: 2, active: 1, draft: 1, trash: 0,
  songs: [
    { id: "song_1", title: "江南", artists: ["林俊杰"], status: "active",
      key: "C", capo: 0, difficulty: "中等", tags: ["流行"], pinyin: "jiang nan",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
    { id: "song_2", title: "十年", artists: ["陈奕迅"], status: "draft",
      key: "G", capo: 2, difficulty: "困难", tags: [], pinyin: "shi nian",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
  ],
};

beforeEach(() => {
  apiRequest.mockReset();
  // 默认返回 2 首歌
  apiRequest.mockImplementation((path: string) => {
    if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
    return Promise.resolve({});
  });
});
afterEach(() => cleanup());

function renderWithToast(ui: React.ReactNode) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("LibraryView 试听入口（M1.5）", () => {
  it("网格卡片右上角 ▶ 图标渲染，aria-label 包含歌名", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    const btn = getByTestId("library-play-song_1");
    expect(btn.getAttribute("aria-label")).toBe("弹唱 江南");
  });

  it("点 ▶ 图标调 onPlaySong(songId) — 不传 link（M1.5 browse 模式）", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_2")).toBeTruthy());
    fireEvent.click(getByTestId("library-play-song_2"));
    expect(onPlaySong).toHaveBeenCalledTimes(1);
    expect(onPlaySong).toHaveBeenCalledWith("song_2");
    // 关键：不传第二个 link 参数（M1.5 由 App.tsx 据此区分 browse vs live）
    expect(onPlaySong.mock.calls[0].length).toBe(1);
  });

  it("点 ▶ 不触发卡片展开（事件 stopPropagation）", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId, queryByTestId } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    fireEvent.click(getByTestId("library-play-song_1"));
    // 卡片展开后才有 library-preview-* 按钮；点击 ▶ 不应该展开
    expect(queryByTestId("library-preview-song_1")).toBeNull();
    expect(onPlaySong).toHaveBeenCalledTimes(1);
  });

  it("展开卡片后操作列出现「试听」按钮（library-preview-）", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    // 展开卡片（点击歌名所在的卡片 body）
    const card = getByTestId("library-play-song_1").closest("div.h-full");
    fireEvent.click(card!);
    await waitFor(() => expect(getByTestId("library-preview-song_1")).toBeTruthy());
    const preview = getByTestId("library-preview-song_1");
    expect(preview.textContent).toContain("试听");
    expect(preview.getAttribute("aria-label")).toBe("试听 江南");
  });

  it("点「试听」按钮调 onPlaySong(songId)", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    // 展开
    const card = getByTestId("library-play-song_1").closest("div.h-full");
    fireEvent.click(card!);
    await waitFor(() => expect(getByTestId("library-preview-song_1")).toBeTruthy());
    apiRequest.mockClear();
    onPlaySong.mockClear();
    fireEvent.click(getByTestId("library-preview-song_1"));
    expect(onPlaySong).toHaveBeenCalledTimes(1);
    expect(onPlaySong).toHaveBeenCalledWith("song_1");
    // 不触发任何后端请求
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("onPlaySong 缺失时 ▶ 与「试听」按钮都不渲染（不影响原有库）", async () => {
    const { queryByTestId, getByTestId } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("library-tab-all")).toBeTruthy());
    expect(queryByTestId("library-play-song_1")).toBeNull();
    expect(queryByTestId("library-preview-song_1")).toBeNull();
  });
});

describe("LibraryView - M9.6b 删除 5s 撤销", () => {
  it("删除歌曲 → 显示 toast「已删除《X》」+ 撤销按钮（默认 5s）", async () => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      // P1-A4: 走 DELETE /api/songs/song_1
      if (path.startsWith("/api/songs/song_")) return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    // 简化流程，跳过 window.confirm
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { getByTestId, getByText } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("library-tab-all")).toBeTruthy());
    // 展开 song_1 → 找「删除」按钮（展开面板操作列里）
    const card = document.querySelectorAll("div.h-full")[0]!;
    fireEvent.click(card);
    await waitFor(() => expect(getByText("删除")).toBeTruthy());
    fireEvent.click(getByText("删除"));
    // 等待 toast 出现
    await waitFor(() => {
      expect(getByTestId("toast-item")).toBeTruthy();
      expect(getByTestId("toast-message").textContent).toBe("已删除「江南」");
      expect(getByTestId("toast-action").textContent).toBe("撤销");
      expect(getByTestId("toast-remaining").textContent).toBe("5s");
    });
  });

  it("点 toast「撤销」→ 调 POST /api/songs/{id}/restore + 显示「已恢复」toast", async () => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      // P1-A4: DELETE /api/songs/{id} + POST /api/songs/{id}/restore
      if (path.startsWith("/api/songs/song_")) return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { getByTestId, getByText } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("library-tab-all")).toBeTruthy());
    const card = document.querySelectorAll("div.h-full")[0]!;
    fireEvent.click(card);
    await waitFor(() => expect(getByText("删除")).toBeTruthy());
    fireEvent.click(getByText("删除"));
    await waitFor(() => expect(getByTestId("toast-action")).toBeTruthy());
    apiRequest.mockClear();
    fireEvent.click(getByTestId("toast-action"));
    await waitFor(() => {
      // restore API 被调
      const calls = apiRequest.mock.calls.map(c => c[0]);
      expect(calls).toContain("/api/songs/song_1/restore");
    });
    // 撤销 toast 消失 + 新 toast「已恢复」
    await waitFor(() => {
      const toasts = document.querySelectorAll('[data-testid="toast-item"]');
      expect(toasts.length).toBe(1);
      expect(getByTestId("toast-message").textContent).toBe("已恢复「江南」");
    });
  });

  it("点 toast ✕ 立即消失（不调 restore）", async () => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      if (path.startsWith("/api/songs/song_")) return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { getByTestId, getByText } = renderWithToast(
      <LibraryView dark={false} onStatsChange={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("library-tab-all")).toBeTruthy());
    const card = document.querySelectorAll("div.h-full")[0]!;
    fireEvent.click(card);
    await waitFor(() => expect(getByText("删除")).toBeTruthy());
    fireEvent.click(getByText("删除"));
    await waitFor(() => expect(getByTestId("toast-close")).toBeTruthy());
    apiRequest.mockClear();
    fireEvent.click(getByTestId("toast-close"));
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
    expect(apiRequest).not.toHaveBeenCalledWith("/api/songs/song_1/restore", expect.anything());
  });
});
