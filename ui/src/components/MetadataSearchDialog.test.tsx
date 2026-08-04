/// M2.9 MetadataSearchDialog 单元测试。
///
/// 覆盖：
/// - 打开时自动调 search API
/// - 展示 hits 列表 + duration 格式化
/// - 点击 hit → 调 song API → onPick
/// - 错误显示（toast 已用 useApiError 处理，行内也显示）
/// - 刷新按钮重跑 search
/// - 空关键词 → 不调 API + 提示
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import MetadataSearchDialog, { type MetadataHit, type MetadataSongDetail } from "./MetadataSearchDialog";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

// 默认注入一个最小 ToastContext（useApiError 内部 useContext）
vi.mock("../components/Toast", () => ({
  ToastContext: {
    Provider: ({ children }: { children: React.ReactNode }) => children,
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() } as any),
}));

const SAMPLE_HITS: MetadataHit[] = [
  {
    source: "netease",
    song_id: "123",
    title: "七里香",
    artist: "周杰伦",
    album: "七里香",
    duration_ms: 234000,
    cover_url: "http://x/c.jpg",
  },
  {
    source: "netease",
    song_id: "456",
    title: "晴天",
    artist: "周杰伦",
    album: "叶惠美",
    duration_ms: 269000,
    cover_url: "http://x/c2.jpg",
  },
];

const SAMPLE_DETAIL: MetadataSongDetail = {
  source: "netease",
  song_id: "123",
  title: "七里香",
  artist: "周杰伦",
  artist_id: "1",
  album: "七里香",
  album_id: "2",
  duration_ms: 234000,
  cover_url: "http://x/c.jpg",
  bpm: null,
};

function setupApiMock() {
  apiRequest.mockReset();
  apiRequest.mockImplementation((path: string) => {
    if (path === "/api/metadata/search") {
      return Promise.resolve({ keyword: "周杰伦", type: "song", provider: "netease", items: SAMPLE_HITS });
    }
    if (path === "/api/metadata/song") {
      return Promise.resolve(SAMPLE_DETAIL);
    }
    return Promise.resolve({});
  });
}

beforeEach(() => {
  setupApiMock();
});
afterEach(() => cleanup());

describe("MetadataSearchDialog", () => {
  it("打开时自动调 search API", async () => {
    render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="周杰伦"
      />,
    );
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/metadata/search",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({ keyword: "周杰伦", type: "song" }),
        }),
      );
    });
  });

  it("展示 hits 列表", async () => {
    const { getAllByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="周杰伦"
      />,
    );
    await waitFor(() => {
      const items = getAllByTestId("hit-item");
      expect(items).toHaveLength(2);
    });
    const items = getAllByTestId("hit-item");
    expect(items[0].getAttribute("data-song-id")).toBe("123");
    expect(items[0].textContent).toContain("七里香");
    expect(items[0].textContent).toContain("周杰伦");
    expect(items[0].textContent).toContain("3:54");  // 234s = 3:54
  });

  it("duration 格式化正确", async () => {
    const single: MetadataHit[] = [{
      source: "netease", song_id: "1", title: "t", artist: "a",
      album: null, duration_ms: 65000, cover_url: null,
    }];
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/search") {
        return Promise.resolve({ keyword: "x", type: "song", provider: "netease", items: single });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="x"
      />,
    );
    await waitFor(() => {
      expect(getByTestId("hit-item").textContent).toContain("1:05");
    });
  });

  it("duration 为 0 / null 显示 —", async () => {
    const single: MetadataHit[] = [{
      source: "netease", song_id: "1", title: "t", artist: "a",
      album: null, duration_ms: null, cover_url: null,
    }];
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/search") {
        return Promise.resolve({ keyword: "x", type: "song", provider: "netease", items: single });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="x"
      />,
    );
    await waitFor(() => {
      expect(getByTestId("hit-item").textContent).toContain("—");
    });
  });

  it("点击 hit → 调 song API → onPick", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    const { getAllByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={onClose}
        onPick={onPick}
        keyword="周杰伦"
      />,
    );
    await waitFor(() => {
      expect(getAllByTestId("hit-item")).toHaveLength(2);
    });
    fireEvent.click(getAllByTestId("hit-item")[0]);
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/metadata/song",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({ song_id: "123", preferred_provider: "netease" }),
        }),
      );
      expect(onPick).toHaveBeenCalledWith(SAMPLE_DETAIL);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("点击 hit 时其他 hit 禁用", async () => {
    const { getAllByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="周杰伦"
      />,
    );
    await waitFor(() => {
      expect(getAllByTestId("hit-item").length).toBe(2);
    });
    // 触发第一个 hit（不等待，因为点击后组件会进入 fetching 状态但 onPick 是 async）
    fireEvent.click(getAllByTestId("hit-item")[0]);
    // 第二个 hit 应被 disabled（fetchingId 不为 null）
    const items = getAllByTestId("hit-item") as HTMLButtonElement[];
    expect(items[1].disabled).toBe(true);
  });

  it("空关键词时显示提示，不调 API", async () => {
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword=""
      />,
    );
    await waitFor(() => {
      expect(getByTestId("empty-keyword")).toBeTruthy();
    });
    // 没调 search
    const searchCalls = apiRequest.mock.calls.filter(([path]) => path === "/api/metadata/search");
    expect(searchCalls).toHaveLength(0);
  });

  it("无结果显示「未找到」", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/search") {
        return Promise.resolve({ keyword: "x", type: "song", provider: "netease", items: [] });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="不存在的歌xyz"
      />,
    );
    await waitFor(() => {
      expect(getByTestId("no-results")).toBeTruthy();
    });
  });

  it("search 失败时显示行内错误", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/search") {
        return Promise.reject(new Error("网络挂了"));
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="x"
      />,
    );
    await waitFor(() => {
      expect(getByTestId("inline-error")).toBeTruthy();
    });
  });

  it("song 失败时显示行内错误", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/search") {
        return Promise.resolve({ keyword: "x", type: "song", provider: "netease", items: SAMPLE_HITS });
      }
      if (path === "/api/metadata/song") {
        return Promise.reject(new Error("歌曲详情失败"));
      }
      return Promise.resolve({});
    });
    const onPick = vi.fn();
    const onClose = vi.fn();
    const { getAllByTestId, getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={onClose}
        onPick={onPick}
        keyword="周杰伦"
      />,
    );
    await waitFor(() => {
      expect(getAllByTestId("hit-item")).toHaveLength(2);
    });
    fireEvent.click(getAllByTestId("hit-item")[0]);
    await waitFor(() => {
      expect(getByTestId("inline-error")).toBeTruthy();
      expect(onPick).not.toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  it("刷新按钮重跑 search", async () => {
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={() => {}}
        onPick={() => {}}
        keyword="周杰伦"
      />,
    );
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(getByTestId("refresh-button"));
    await waitFor(() => {
      expect(apiRequest.mock.calls.filter(([p]) => p === "/api/metadata/search")).toHaveLength(2);
    });
  });

  it("关闭按钮调 onClose", async () => {
    const onClose = vi.fn();
    const { getByTestId } = render(
      <MetadataSearchDialog
        open
        onClose={onClose}
        onPick={() => {}}
        keyword="周杰伦"
      />,
    );
    fireEvent.click(getByTestId("close-button"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("open=false 时不调 search", () => {
    render(
      <MetadataSearchDialog
        open={false}
        onClose={() => {}}
        onPick={() => {}}
        keyword="周杰伦"
      />,
    );
    const searchCalls = apiRequest.mock.calls.filter(([p]) => p === "/api/metadata/search");
    expect(searchCalls).toHaveLength(0);
  });
});
