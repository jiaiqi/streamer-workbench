/// WorkspacePosterBridge 单元测试：theme_id / canvas_id 同步到父级。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import WorkspacePosterBridge from "./WorkspacePosterBridge";

// Mock usePosterStore to keep test independent of hook implementation.
let mockStoreState: any = {};
vi.mock("./usePosterStore", () => ({
  usePosterStore: () => mockStoreState,
}));

vi.mock("./PostersSidebar", () => ({
  default: () => <div data-testid="sidebar">sidebar</div>,
}));
vi.mock("./SongSourcePicker", () => ({
  default: () => <div data-testid="picker">picker</div>,
}));

beforeEach(() => {
  mockStoreState = {
    current: {
      theme_id: "海洋柔光",
      canvas_id: "9:20",
      song_source: { type: "all_active", artists: [] },
      selected_song_ids: [],
      name: "doc",
    },
    revision: "",
    status: "idle",
    lastSavedAt: null,
    error: null,
    posters: [],
    refreshList: vi.fn(async () => undefined),
    select: vi.fn(async () => undefined),
    newDraft: vi.fn(),
    update: vi.fn(),
    saveNow: vi.fn(async () => null),
    flush: vi.fn(async () => undefined),
    deleteCurrent: vi.fn(async () => undefined),
    cancel: vi.fn(),
    resetError: vi.fn(),
    isDirty: false,
  };
});

afterEach(() => vi.restoreAllMocks());

describe("WorkspacePosterBridge", () => {
  it("渲染 sidebar + picker", () => {
    render(
      <WorkspacePosterBridge
        dark={false}
        availableThemeNames={["海洋柔光"]}
        onThemeSelect={vi.fn()}
        onCanvasSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId("sidebar")).toBeTruthy();
    expect(screen.getByTestId("picker")).toBeTruthy();
  });

  it("theme_id 变化时回调 onThemeSelect（仅当在 availableThemeNames）", async () => {
    const onTheme = vi.fn();
    const { rerender } = render(
      <WorkspacePosterBridge
        dark={false}
        availableThemeNames={["海洋柔光", "奶油玻璃"]}
        onThemeSelect={onTheme}
        onCanvasSelect={vi.fn()}
      />,
    );
    // 首次渲染：theme_id="海洋柔光" → 调用一次
    expect(onTheme).toHaveBeenCalledWith("海洋柔光");

    // 改 theme_id → 第二次调用
    mockStoreState.current.theme_id = "奶油玻璃";
    rerender(
      <WorkspacePosterBridge
        dark={false}
        availableThemeNames={["海洋柔光", "奶油玻璃"]}
        onThemeSelect={onTheme}
        onCanvasSelect={vi.fn()}
      />,
    );
    expect(onTheme).toHaveBeenCalledWith("奶油玻璃");
  });

  it("theme_id 不在 availableThemeNames 时不回调", async () => {
    const onTheme = vi.fn();
    mockStoreState.current.theme_id = "不存在的";
    render(
      <WorkspacePosterBridge
        dark={false}
        availableThemeNames={["海洋柔光"]}
        onThemeSelect={onTheme}
        onCanvasSelect={vi.fn()}
      />,
    );
    expect(onTheme).not.toHaveBeenCalled();
  });

  it("canvas_id 变化时回调 onCanvasSelect", async () => {
    const onCanvas = vi.fn();
    const { rerender } = render(
      <WorkspacePosterBridge
        dark={false}
        availableThemeNames={["海洋柔光"]}
        onThemeSelect={vi.fn()}
        onCanvasSelect={onCanvas}
      />,
    );
    expect(onCanvas).toHaveBeenCalledWith("9:20");

    mockStoreState.current.canvas_id = "9:16";
    rerender(
      <WorkspacePosterBridge
        dark={false}
        availableThemeNames={["海洋柔光"]}
        onThemeSelect={vi.fn()}
        onCanvasSelect={onCanvas}
      />,
    );
    expect(onCanvas).toHaveBeenCalledWith("9:16");
  });
});
