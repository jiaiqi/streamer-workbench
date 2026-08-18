/// DataQuickEntryCard 单元测试（R4.2.4 1.1 收口）。
///
/// 覆盖：
/// - loading 态：初始渲染时显示 Spinner
/// - error 态：fetch 失败时显示 ErrorBanner + 重试按钮
/// - empty 态：items=[] 时显示 EmptyState + "去看统计" 按钮
/// - data 态：items.length=3 时显示列表 + 创建海报按钮
/// - data 态：点击创建按钮触发 onCreatePosterFromTop（songIds 数组）
/// - data 态：点击"更多 →"触发 onSwitchToStats

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/client")>();
  return { ...original, apiRequest: vi.fn() };
});

import { apiRequest } from "@/api/client";
import DataQuickEntryCard from "./DataQuickEntryCard";

const fakeTop = {
  metric: "request",
  note: "",
  items: [
    { song_id: "s1", title: "晴天", artist: "周杰伦", count: 12, minutes: 0 },
    { song_id: "s2", title: "十年", artist: "陈奕迅", count: 8, minutes: 0 },
    { song_id: "s3", title: "倔强", artist: "五月天", count: 5, minutes: 0 },
  ],
};

beforeEach(() => {
  vi.mocked(apiRequest).mockReset();
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("DataQuickEntryCard", () => {
  it("loading 态：渲染 Spinner 占位", () => {
    vi.mocked(apiRequest).mockReturnValue(new Promise(() => { /* never resolve */ }));
    render(<DataQuickEntryCard dark={false} onCreatePosterFromTop={vi.fn()} onSwitchToStats={vi.fn()} />);
    expect(screen.getByTestId("data-quick-loading")).toBeTruthy();
    expect(screen.getByText(/加载点歌热度中/)).toBeTruthy();
  });

  it("error 态：fetch 失败显示 ErrorBanner", async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error("后端失联"));
    render(<DataQuickEntryCard dark={false} onCreatePosterFromTop={vi.fn()} onSwitchToStats={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId("data-quick-error")).toBeTruthy();
    });
    expect(screen.getByText(/后端失联/)).toBeTruthy();
  });

  it("empty 态：items=[] 显示 EmptyState + 去看统计", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ metric: "request", note: "数据不足时累计 30 天点歌", items: [] });
    render(<DataQuickEntryCard dark={false} onCreatePosterFromTop={vi.fn()} onSwitchToStats={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId("data-quick-empty")).toBeTruthy();
    });
    expect(screen.getByText(/还没有点歌记录/)).toBeTruthy();
    const statsBtn = screen.getByRole("button", { name: /去看统计/ });
    expect(statsBtn).toBeTruthy();
  });

  it("data 态：3 首歌 + 创建按钮 + 统计链接", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(fakeTop);
    render(<DataQuickEntryCard dark={false} onCreatePosterFromTop={vi.fn()} onSwitchToStats={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId("data-quick-list")).toBeTruthy();
    });
    // 3 首歌：data-quick-item 出现 3 次
    expect(screen.getAllByTestId("data-quick-item").length).toBe(3);
    // 3 首歌的标题都渲染
    expect(screen.getByText("晴天")).toBeTruthy();
    expect(screen.getByText("十年")).toBeTruthy();
    expect(screen.getByText("倔强")).toBeTruthy();
    // 计数
    expect(screen.getByText("×12")).toBeTruthy();
    // 创建按钮
    const createBtn = screen.getByTestId("data-quick-create");
    expect(createBtn.textContent).toContain("用 Top 3 创建海报");
    // 统计链接
    expect(screen.getByTestId("data-quick-stats-link")).toBeTruthy();
  });

  it("data 态：点击创建按钮触发 onCreatePosterFromTop 传 songIds 数组", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(fakeTop);
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onSwitch = vi.fn();
    const user = userEvent.setup();
    render(<DataQuickEntryCard dark={false} onCreatePosterFromTop={onCreate} onSwitchToStats={onSwitch} />);
    await waitFor(() => screen.getByTestId("data-quick-create"));
    await user.click(screen.getByTestId("data-quick-create"));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledTimes(1);
    });
    // 传入的应是 3 个 song_id 数组（顺序保留）
    expect(onCreate).toHaveBeenCalledWith(["s1", "s2", "s3"]);
    // 切到 stats 不应被触发
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it("data 态：点击\"更多 →\"触发 onSwitchToStats", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(fakeTop);
    const onCreate = vi.fn();
    const onSwitch = vi.fn();
    const user = userEvent.setup();
    render(<DataQuickEntryCard dark={false} onCreatePosterFromTop={onCreate} onSwitchToStats={onSwitch} />);
    await waitFor(() => screen.getByTestId("data-quick-stats-link"));
    await user.click(screen.getByTestId("data-quick-stats-link"));
    expect(onSwitch).toHaveBeenCalledTimes(1);
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("data 态：暗色模式 class 正确", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(fakeTop);
    const { container } = render(
      <DataQuickEntryCard dark={true} onCreatePosterFromTop={vi.fn()} onSwitchToStats={vi.fn()} />,
    );
    await waitFor(() => screen.getByTestId("data-quick-list"));
    // 暗色 class 包含 border-zinc-700/50
    expect(container.querySelector('[data-testid="data-quick-entry"]')?.className).toContain("border-zinc-700/50");
  });
});
