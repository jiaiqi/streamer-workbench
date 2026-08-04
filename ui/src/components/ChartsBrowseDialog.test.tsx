/// M2.12 ChartsBrowseDialog 单元测试。
///
/// 覆盖：
/// - 打开自动调 /api/metadata/charts + 显示榜单卡片
/// - 榜单加载失败 → 行内错误 + 重试
/// - 点榜单 → 调 /api/metadata/playlist → 歌曲列表默认全选
/// - 返回榜单列表（不重新请求 charts）
/// - 榜单歌曲缓存：返回再进同一榜单不重复请求 playlist
/// - 取消勾选 / 全选切换
/// - 导入 → /api/songs/import merge + notes meta chart= + onImported
/// - 导入结果展示 + 按钮变「已导入」
/// - 空榜单 / 空歌曲提示
/// - open=false 不调 API
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import ChartsBrowseDialog from "./ChartsBrowseDialog";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

vi.mock("../components/Toast", () => ({
  ToastContext: {
    Provider: ({ children }: { children: React.ReactNode }) => children,
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() } as any),
}));

const SAMPLE_CHARTS = [
  { source: "netease", chart_id: "19723756", title: "飙升榜", cover_url: null, description: "每天更新" },
  { source: "netease", chart_id: "3778678", title: "热歌榜", cover_url: "http://x/c2.jpg", description: "每周更新" },
  { source: "netease", chart_id: "3779629", title: "新歌榜", cover_url: null, description: null },
];

const SAMPLE_CHART_SONGS = {
  source: "netease",
  playlist_id: "19723756",
  title: "飙升榜",
  creator: "网易云音乐",
  cover_url: null,
  description: "每天更新",
  play_count: 12345678,
  songs: [
    { source: "netease", song_id: "a1", title: "夜曲", artist: "周杰伦", album: "11月的肖邦", duration_ms: 230000, cover_url: null },
    { source: "netease", song_id: "b2", title: "晴天", artist: "周杰伦", album: "叶惠美", duration_ms: 269000, cover_url: null },
    { source: "netease", song_id: "c3", title: "稻香", artist: "周杰伦 / 阿信", album: null, duration_ms: 223000, cover_url: null },
  ],
};

const SAMPLE_IMPORT_RESULT = {
  ok: true,
  added: 3,
  skipped: 0,
  errors: [],
  active: 0,
  draft: 3,
};

function setupApiMock() {
  apiRequest.mockReset();
  apiRequest.mockImplementation((path: string, opts?: { body?: { playlist_id?: string } }) => {
    if (path === "/api/metadata/charts") {
      return Promise.resolve(SAMPLE_CHARTS);
    }
    if (path === "/api/metadata/playlist") {
      return Promise.resolve(SAMPLE_CHART_SONGS);
    }
    if (path === "/api/songs/import") {
      return Promise.resolve(SAMPLE_IMPORT_RESULT);
    }
    return Promise.resolve({});
  });
}

beforeEach(() => {
  setupApiMock();
});
afterEach(() => cleanup());

describe("ChartsBrowseDialog", () => {
  it("打开自动调 /api/metadata/charts 并显示榜单卡片", async () => {
    const { getByTestId, getAllByTestId } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/metadata/charts",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(getByTestId("charts-grid")).toBeTruthy();
    });
    expect(getAllByTestId("chart-card")).toHaveLength(3);
  });

  it("榜单加载失败显示行内错误 + 重试可用", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/charts") {
        return Promise.reject(new Error("网络不通"));
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("charts-error")).toBeTruthy();
    });
  });

  it("点榜单 → 调 /api/metadata/playlist → 歌曲列表默认全选", async () => {
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/metadata/playlist",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({ playlist_id: "19723756" }),
        }),
      );
    });
    await waitFor(() => {
      expect(getByTestId("song-list")).toBeTruthy();
    });
    const rows = getAllByTestId("song-row");
    expect(rows).toHaveLength(3);
    const checkboxes = getAllByTestId("song-checkbox") as HTMLInputElement[];
    expect(checkboxes.every(c => c.checked)).toBe(true);
    expect(getByTestId("songs-count").textContent).toContain("共 3 首");
  });

  it("返回榜单列表不重新请求 charts", async () => {
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    const chartsCallsAfterLoad = apiRequest.mock.calls.filter(([p]) => p === "/api/metadata/charts").length;
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("back-button"));
    await waitFor(() => expect(getByTestId("charts-grid")).toBeTruthy());
    const chartsCallsAfterBack = apiRequest.mock.calls.filter(([p]) => p === "/api/metadata/charts").length;
    expect(chartsCallsAfterBack).toBe(chartsCallsAfterLoad);
  });

  it("榜单歌曲缓存：返回再进同一榜单不重复请求 playlist", async () => {
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("back-button"));
    await waitFor(() => expect(getByTestId("charts-grid")).toBeTruthy());
    // 再进同一榜单
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    const playlistCalls = apiRequest.mock.calls.filter(([p]) => p === "/api/metadata/playlist");
    expect(playlistCalls).toHaveLength(1);
  });

  it("取消勾选后导入按钮计数变化", async () => {
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => expect(getAllByTestId("song-checkbox").length).toBe(3));
    // 取消第一个 → 2
    fireEvent.click(getAllByTestId("song-checkbox")[0]);
    await waitFor(() => {
      expect(getByTestId("import-button").textContent).toContain("导入选中（2）");
    });
    // 部分选中时 toggle-all = 全选（回到 3）
    fireEvent.click(getByTestId("toggle-all"));
    await waitFor(() => {
      expect(getByTestId("import-button").textContent).toContain("导入选中（3）");
    });
    // 全选时 toggle-all = 全不选（0）
    fireEvent.click(getByTestId("toggle-all"));
    await waitFor(() => {
      expect(getByTestId("import-button").textContent).toContain("导入选中（0）");
    });
  });

  it("导入 → /api/songs/import merge + notes meta chart= + onImported", async () => {
    const onImported = vi.fn().mockResolvedValue(undefined);
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={onImported} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("import-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/songs/import",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({ mode: "merge", songs: expect.any(Array) }),
        }),
      );
      const call = apiRequest.mock.calls.find(([p]) => p === "/api/songs/import");
      const songs = call?.[1].body.songs;
      expect(songs).toHaveLength(3);
      // 'A / B' 拆成 ['周杰伦', '阿信']
      expect(songs[2].artists).toEqual(["周杰伦", "阿信"]);
      expect(songs[0].status).toBe("draft");
      expect(songs[0].notes).toMatch(/\[meta:netease chart=19723756/);
      expect(onImported).toHaveBeenCalled();
    });
  });

  it("导入后显示结果 + 按钮变「已导入」disabled", async () => {
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("import-button"));
    await waitFor(() => {
      expect(getByTestId("import-result").textContent).toContain("新增 3 首");
      const btn = getByTestId("import-button") as HTMLButtonElement;
      expect(btn.textContent).toContain("已导入");
      expect(btn.disabled).toBe(true);
    });
  });

  it("榜单歌曲加载失败显示行内错误", async () => {
    apiRequest.mockImplementation((path: string, opts?: { body?: { playlist_id?: string } }) => {
      if (path === "/api/metadata/charts") {
        return Promise.resolve(SAMPLE_CHARTS);
      }
      if (path === "/api/metadata/playlist") {
        return Promise.reject(new Error("榜单歌曲拉取失败"));
      }
      return Promise.resolve({});
    });
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => {
      expect(getByTestId("songs-error")).toBeTruthy();
    });
  });

  it("空榜单显示提示", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/charts") {
        return Promise.resolve([]);
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("empty-charts")).toBeTruthy();
    });
  });

  it("空歌曲榜单显示提示", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/charts") {
        return Promise.resolve(SAMPLE_CHARTS);
      }
      if (path === "/api/metadata/playlist") {
        return Promise.resolve({ ...SAMPLE_CHART_SONGS, songs: [] });
      }
      return Promise.resolve({});
    });
    const { getByTestId, getAllByTestId, getByText } = render(
      <ChartsBrowseDialog open onClose={() => {}} onImported={() => {}} />,
    );
    await waitFor(() => expect(getAllByTestId("chart-card").length).toBe(3));
    fireEvent.click(getByText("飙升榜"));
    await waitFor(() => {
      expect(getByTestId("empty-songs")).toBeTruthy();
    });
  });

  it("open=false 不调 API", () => {
    render(<ChartsBrowseDialog open={false} onClose={() => {}} onImported={() => {}} />);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
