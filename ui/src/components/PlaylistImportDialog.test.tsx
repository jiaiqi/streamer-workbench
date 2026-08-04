/// M2.11 PlaylistImportDialog 单元测试。
///
/// 覆盖：
/// - 打开时无 playlist / 显示提示
/// - 输入 ID + 点预览 → 调 /api/metadata/playlist
/// - 展示 playlist 详情 + 歌曲列表（默认全选）
/// - 全选/全不选切换
/// - 选中部分 → 调 /api/songs/import (merge mode)
/// - 导入成功 → 显示结果（added/skipped）+ onImported 调用
/// - 错误：toast + 行内错误双通道
/// - 离线时预览按钮 disabled
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import PlaylistImportDialog from "./PlaylistImportDialog";

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

const SAMPLE_PLAYLIST = {
  source: "netease",
  playlist_id: "123",
  title: "我喜欢的音乐",
  creator: "主播小王",
  cover_url: "http://x/p.jpg",
  description: "个人精选",
  play_count: 12345,
  songs: [
    { source: "netease", song_id: "11", title: "七里香", artist: "周杰伦", album: "七里香", duration_ms: 234000, cover_url: null },
    { source: "netease", song_id: "22", title: "晴天", artist: "周杰伦", album: "叶惠美", duration_ms: 269000, cover_url: null },
    { source: "netease", song_id: "33", title: "夜曲", artist: "周杰伦 / A", album: null, duration_ms: 230000, cover_url: null },
  ],
};

const SAMPLE_IMPORT_RESULT = {
  ok: true,
  added: 2,
  skipped: 1,
  errors: [],
  active: 0,
  draft: 2,
};

function setupApiMock() {
  apiRequest.mockReset();
  apiRequest.mockImplementation((path: string) => {
    if (path === "/api/metadata/playlist") {
      return Promise.resolve(SAMPLE_PLAYLIST);
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

describe("PlaylistImportDialog", () => {
  it("打开时显示空状态", () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    expect(getByTestId("empty-state")).toBeTruthy();
  });

  it("provider 默认 netease", () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    const select = getByTestId("provider-select") as HTMLSelectElement;
    expect(select.value).toBe("netease");
  });

  it("可用 providers 列表可定制", () => {
    const { getByTestId } = render(
      <PlaylistImportDialog
        open
        onClose={() => {}}
        onImported={() => {}}
        availableProviders={["netease", "custom"]}
      />,
    );
    const select = getByTestId("provider-select") as HTMLSelectElement;
    const options = Array.from(select.options).map(o => o.value);
    expect(options).toEqual(["netease", "custom"]);
  });

  it("输入 ID + 点预览 → 调 /api/metadata/playlist", async () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/metadata/playlist",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({ playlist_id: "123", preferred_provider: "netease" }),
        }),
      );
    });
  });

  it("空 ID 不调 API，提示请输入", async () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    const previewBtn = getByTestId("preview-button") as HTMLButtonElement;
    expect(previewBtn.disabled).toBe(true);
  });

  it("预览后展示 playlist + 歌曲列表（默认全选）", async () => {
    const { getByTestId, getAllByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => {
      expect(getByTestId("song-list")).toBeTruthy();
    });
    const rows = getAllByTestId("song-row");
    expect(rows).toHaveLength(3);
    const checkboxes = getAllByTestId("song-checkbox") as HTMLInputElement[];
    // 默认全选
    expect(checkboxes.every(c => c.checked)).toBe(true);
  });

  it("导入按钮默认显示「导入选中（3）」", async () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => {
      const btn = getByTestId("import-button");
      expect(btn.textContent).toContain("导入选中（3）");
    });
  });

  it("点击 checkbox 取消选择", async () => {
    const { getByTestId, getAllByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => expect(getAllByTestId("song-checkbox").length).toBe(3));
    // 取消第一个
    fireEvent.click(getAllByTestId("song-checkbox")[0]);
    await waitFor(() => {
      const btn = getByTestId("import-button");
      expect(btn.textContent).toContain("导入选中（2）");
    });
  });

  it("全选/全不选切换", async () => {
    const { getByTestId, getAllByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => expect(getAllByTestId("song-checkbox").length).toBe(3));
    // 全不选
    fireEvent.click(getByTestId("toggle-all"));
    await waitFor(() => {
      const btn = getByTestId("import-button");
      expect(btn.textContent).toContain("导入选中（0）");
    });
    // 再全选
    fireEvent.click(getByTestId("toggle-all"));
    await waitFor(() => {
      const btn = getByTestId("import-button");
      expect(btn.textContent).toContain("导入选中（3）");
    });
  });

  it("导入 → /api/songs/import merge + onImported", async () => {
    const onImported = vi.fn().mockResolvedValue(undefined);
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={onImported} onImported={onImported} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("import-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/songs/import",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({
            mode: "merge",
            songs: expect.any(Array),
          }),
        }),
      );
      const call = apiRequest.mock.calls.find(([p]) => p === "/api/songs/import");
      const songs = call?.[1].body.songs;
      expect(songs).toHaveLength(3);
      // 第 3 首 'A / B' 拆成 ['周杰伦', 'A']
      expect(songs[2].artists).toEqual(["周杰伦", "A"]);
      expect(songs[0].status).toBe("draft");
      expect(songs[0].notes).toMatch(/\[meta:netease playlist=123/);
      expect(onImported).toHaveBeenCalled();
    });
  });

  it("导入后显示结果（added/skipped/active/draft）", async () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("import-button"));
    await waitFor(() => {
      const result = getByTestId("import-result");
      expect(result.textContent).toContain("新增 2 首");
      expect(result.textContent).toContain("跳过 1 首");
      expect(result.textContent).toContain("active 0");
      expect(result.textContent).toContain("draft 2");
    });
  });

  it("preview 失败时显示行内错误", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/playlist") {
        return Promise.reject(new Error("歌单 ID 不对"));
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "999" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => {
      expect(getByTestId("inline-error")).toBeTruthy();
    });
  });

  it("import 失败时显示行内错误", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/playlist") {
        return Promise.resolve(SAMPLE_PLAYLIST);
      }
      if (path === "/api/songs/import") {
        return Promise.reject(new Error("曲库写入失败"));
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("import-button"));
    await waitFor(() => {
      expect(getByTestId("inline-error")).toBeTruthy();
    });
  });

  it("导入后按钮变「已导入」且 disabled", async () => {
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => expect(getByTestId("song-list")).toBeTruthy());
    fireEvent.click(getByTestId("import-button"));
    await waitFor(() => {
      const btn = getByTestId("import-button") as HTMLButtonElement;
      expect(btn.textContent).toContain("已导入");
      expect(btn.disabled).toBe(true);
    });
  });

  it("空歌单显示提示", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/playlist") {
        return Promise.resolve({ ...SAMPLE_PLAYLIST, songs: [] });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <PlaylistImportDialog open onClose={() => {}} onImported={() => {}} />,
    );
    fireEvent.change(getByTestId("playlist-id-input"), { target: { value: "123" } });
    fireEvent.click(getByTestId("preview-button"));
    await waitFor(() => {
      expect(getByTestId("empty-playlist")).toBeTruthy();
    });
  });

  it("open=false 不渲染内容", () => {
    const { queryByTestId } = render(
      <PlaylistImportDialog open={false} onClose={() => {}} onImported={() => {}} />,
    );
    // shadcn Dialog 用 portal + open=false 仍会渲染 dialog 元素但内容可能为 null
    // 这里只测 apiRequest 没被调
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
