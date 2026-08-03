/// L2.1 批量操作测试（多选 + 批量删除/改状态）
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import LibraryView from "./LibraryView";
import { ToastProvider } from "../components/Toast";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const SONGS_DATA = {
  total: 3, active: 1, draft: 2, trash: 0,
  songs: [
    { id: "song_1", title: "江南", artists: ["林俊杰"], status: "active",
      key: "C", capo: 0, difficulty: "中等", tags: ["流行"], pinyin: "jiang nan",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
    { id: "song_2", title: "十年", artists: ["陈奕迅"], status: "draft",
      key: "G", capo: 2, difficulty: "困难", tags: [], pinyin: "shi nian",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
    { id: "song_3", title: "后来", artists: ["刘若英"], status: "draft",
      key: "D", capo: 0, difficulty: "简单", tags: [], pinyin: "hou lai",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
  ],
};

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockImplementation((path: string) => {
    if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
    return Promise.resolve({});
  });
  // 默认 window.confirm 返回 true
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderLibrary() {
  return render(
    <ToastProvider>
      <LibraryView dark={false} onStatsChange={vi.fn()} />
    </ToastProvider>,
  );
}

async function waitForSongs() {
  await waitFor(() => {
    expect(apiRequest).toHaveBeenCalledWith("/api/songs/list", expect.anything());
  });
}

describe("L2.1 LibraryView 批量操作", () => {
  it("默认无 select 模式，action bar 不显示", async () => {
    const { queryByTestId } = renderLibrary();
    await waitForSongs();
    expect(queryByTestId("library-batch-bar")).toBeNull();
  });

  it("点「选择」按钮进入 select 模式，action bar 出现 + 显示 0 首", async () => {
    const { getByTestId, queryByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    expect(queryByTestId("library-batch-bar")).toBeTruthy();
    expect(getByTestId("library-batch-count").textContent).toBe("0");
  });

  it("点「退出选择」回到正常模式，action bar 消失", async () => {
    const { getByTestId, queryByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    expect(queryByTestId("library-batch-bar")).toBeTruthy();
    fireEvent.click(getByTestId("library-batch-cancel"));
    expect(queryByTestId("library-batch-bar")).toBeNull();
  });

  it("select 模式下点击卡片 toggle 选中 + 计数 +1", async () => {
    const { getByTestId, queryByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    // 取消 select 时点击 1 不展开而是 toggleSelect
    expect(queryByTestId("library-batch-bar")).toBeTruthy();
    fireEvent.click(getByTestId("library-card-song_1"));
    expect(getByTestId("library-batch-count").textContent).toBe("1");
    // checkbox 视觉标记
    const cb = getByTestId("library-card-checkbox-song_1");
    expect(cb.getAttribute("data-checked")).toBe("true");
    // 再点一次取消
    fireEvent.click(getByTestId("library-card-song_1"));
    expect(getByTestId("library-batch-count").textContent).toBe("0");
  });

  it("「全选当前筛选」选中所有当前可见歌曲", async () => {
    const { getByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-batch-select-all"));
    expect(getByTestId("library-batch-count").textContent).toBe("3");
  });

  it("「清空」清空当前选择", async () => {
    const { getByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-batch-select-all"));
    expect(getByTestId("library-batch-count").textContent).toBe("3");
    fireEvent.click(getByTestId("library-batch-clear"));
    expect(getByTestId("library-batch-count").textContent).toBe("0");
  });

  it("批量删除：选中 N 首 → 调 N 次 delete API + 弹聚合 toast「已删除 N 首」+ 退 select 模式", async () => {
    const { getByTestId, queryByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-card-song_1"));
    fireEvent.click(getByTestId("library-card-song_2"));
    expect(getByTestId("library-batch-count").textContent).toBe("2");

    apiRequest.mockClear();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/delete") return Promise.resolve({ ok: true });
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      return Promise.resolve({});
    });

    fireEvent.click(getByTestId("library-batch-delete"));
    await waitFor(() => {
      const deletes = apiRequest.mock.calls.filter(([p]) => p === "/api/songs/delete");
      expect(deletes.length).toBe(2);
    });
    // 弹 toast「已删除 2 首」
    await waitFor(() => {
      const toasts = document.querySelectorAll('[data-testid="toast-item"]');
      expect(toasts.length).toBe(1);
      expect(toasts[0].textContent).toContain("已删除 2 首");
    });
    // 退 select 模式
    expect(queryByTestId("library-batch-bar")).toBeNull();
  });

  it("批量删除：单首走 M9.6b 撤销逻辑（5s 撤销 + restore 端点）", async () => {
    const { getByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-card-song_1"));
    expect(getByTestId("library-batch-count").textContent).toBe("1");

    apiRequest.mockClear();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/delete") return Promise.resolve({ ok: true });
      if (path.startsWith("/api/songs/song_1/restore")) return Promise.resolve({ ok: true });
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      return Promise.resolve({});
    });

    fireEvent.click(getByTestId("library-batch-delete"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith("/api/songs/delete", expect.anything());
    });
    // 单条 toast 带撤销按钮
    await waitFor(() => {
      const toasts = document.querySelectorAll('[data-testid="toast-item"]');
      expect(toasts.length).toBe(1);
      expect(toasts[0].textContent).toContain("已删除「江南」");
      // 撤销按钮在 toast 内
      expect(toasts[0].querySelector("button")).toBeTruthy();
    });
  });

  it("批量标记已会：选中 N 首 draft → 调 N 次 status API + 弹「已标记 N 首为已会」", async () => {
    const { getByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-card-song_2"));
    fireEvent.click(getByTestId("library-card-song_3"));
    expect(getByTestId("library-batch-count").textContent).toBe("2");

    apiRequest.mockClear();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/status") return Promise.resolve({ ok: true, status: "active" });
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      return Promise.resolve({});
    });

    fireEvent.click(getByTestId("library-batch-mark-active"));
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(([p]) => p === "/api/songs/status");
      expect(calls.length).toBe(2);
    });
    await waitFor(() => {
      const toasts = document.querySelectorAll('[data-testid="toast-item"]');
      expect(toasts.length).toBe(1);
      expect(toasts[0].textContent).toContain("已标记 2 首为已会");
    });
  });

  it("批量标记未会：选中 active 歌曲 → 弹「已标记 N 首为未会」", async () => {
    const { getByTestId } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-card-song_1"));  // 江南 = active

    apiRequest.mockClear();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/songs/status") return Promise.resolve({ ok: true, status: "draft" });
      if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
      return Promise.resolve({});
    });

    fireEvent.click(getByTestId("library-batch-mark-draft"));
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(([p]) => p === "/api/songs/status");
      expect(calls.length).toBe(1);
    });
    await waitFor(() => {
      const toasts = document.querySelectorAll('[data-testid="toast-item"]');
      expect(toasts[0].textContent).toContain("已标记 1 首为未会");
    });
  });

  it("select 模式下点击卡片不展开（点击行为改为 toggle select）", async () => {
    const { getByTestId, queryByText } = renderLibrary();
    await waitForSongs();
    fireEvent.click(getByTestId("library-select-toggle"));
    fireEvent.click(getByTestId("library-card-song_1"));
    // 不应该看到展开的「作词」字段（展开面板的标志）
    expect(queryByText("作词")).toBeNull();
  });
});
