/// PostersSidebar 单元测试：覆盖「新建/选中/删除/搜索/排序/右键/inline rename/缩略图/重做」。
///
/// M3 P0 新增覆盖：
/// - 搜索框过滤（按 name 子串，大小写不敏感）
/// - 排序下拉（updated / name / songs 三种）
/// - 右键菜单（重命名/复制副本/删除）
/// - inline 重命名（双击 / 右键 / 失焦提交 / Enter 提交 / Esc 取消 / 空名拒绝）
/// - 当前海报重命名走 store.rename，非当前走独立 PATCH
/// - 复制当前海报走 store.duplicate
/// - 缩略图 fallback（img 加载失败时显示首字符）
/// - 撤销/重做按钮可见性
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PostersSidebar from "./PostersSidebar";
import type { PosterStore } from "./usePosterStore";

function makeFakeStore(overrides: Partial<PosterStore> = {}): PosterStore {
  const noop = () => undefined;
  return {
    current: {
      name: "我的第一张",
      song_source: { type: "all_active", artists: [] },
      selected_song_ids: [],
      grouping: "none",
      sorting: "manual",
      layout_id: "grid-wrap",
      theme_id: "海洋柔光",
      canvas_id: "9:20",
      page_policy: { mode: "legacy-fixed-2" },
      parameters: {},
      export_settings: {
        format: "png", jpeg_quality: 92, single_page: false, dpi: 144,
      },
    },
    revision: "",
    status: "idle",
    lastSavedAt: null,
    error: null,
    posters: [
      {
        id: "poster_1", name: "已保存1", layout_id: "grid-wrap",
        theme_id: "海洋柔光", canvas_id: "9:20",
        created_at: "2026-07-30T00:00:00", updated_at: "2026-07-30T00:00:00",
        song_count: 12,
      },
      {
        id: "poster_2", name: "已保存2", layout_id: "grid-wrap",
        theme_id: "海洋柔光", canvas_id: "9:20",
        created_at: "2026-07-30T00:00:00", updated_at: "2026-07-30T00:00:00",
        song_count: 7,
      },
      {
        id: "poster_3", name: "演唱回顾", layout_id: "grid-wrap",
        theme_id: "海洋柔光", canvas_id: "9:20",
        created_at: "2026-07-30T00:00:00", updated_at: "2026-07-30T00:00:00",
        song_count: 25,
      },
    ],
    refreshList: vi.fn(async () => undefined),
    select: vi.fn(async () => undefined),
    newDraft: vi.fn(noop),
    update: vi.fn(noop),
    saveNow: vi.fn(async () => null),
    flush: vi.fn(async () => undefined),
    deleteCurrent: vi.fn(async () => undefined),
    cancel: vi.fn(noop),
    resetError: vi.fn(noop),
    isDirty: false,
    rename: vi.fn(async (name: string) => name),
    duplicate: vi.fn(async () => "new_poster_id"),
    undo: vi.fn(noop),
    redo: vi.fn(noop),
    canUndo: true,
    canRedo: false,
    ...overrides,
  } as unknown as PosterStore;
}

let confirmSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  confirmSpy.mockRestore();
});

describe("PostersSidebar - 基础", () => {
  it("显示当前海报名称", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    expect(screen.getByText("我的第一张")).toBeTruthy();
  });

  it("显示已保存的海报列表（来自 store.posters）", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    expect(screen.getByText("已保存1")).toBeTruthy();
    expect(screen.getByText("已保存2")).toBeTruthy();
    expect(screen.getByText("演唱回顾")).toBeTruthy();
  });

  it("新建按钮调用 newDraft", async () => {
    const store = makeFakeStore();
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByRole("button", { name: /新建/ }));
    expect(store.newDraft).toHaveBeenCalledTimes(1);
  });

  it("点击列表项触发 select(id)", async () => {
    const store = makeFakeStore();
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByText("已保存1"));
    expect(store.select).toHaveBeenCalledWith("poster_1");
  });

  it("current.id 为空时不显示删除按钮", () => {
    render(<PostersSidebar store={makeFakeStore({ revision: "" })} dark={false} />);
    expect(screen.queryByRole("button", { name: "删除当前" })).toBeNull();
  });

  it("current.id 存在时显示删除按钮 + 确认弹窗", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_cur" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByRole("button", { name: "删除当前" }));
    expect(window.confirm).toHaveBeenCalled();
    expect(store.deleteCurrent).toHaveBeenCalledTimes(1);
  });

  it("error 态显示重试按钮", async () => {
    const store = makeFakeStore({
      status: "error",
      error: { message: "网络中断", recovery: "重试" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(store.saveNow).toHaveBeenCalledTimes(1);
  });

  it("撤销/重做按钮按 canUndo/canRedo 状态启用", async () => {
    const user = userEvent.setup();
    const store1 = makeFakeStore({ canUndo: false, canRedo: false });
    const { rerender } = render(<PostersSidebar store={store1} dark={false} />);
    expect((screen.getByTestId("poster-undo") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("poster-redo") as HTMLButtonElement).disabled).toBe(true);

    const store2 = makeFakeStore({ canUndo: true, canRedo: true });
    rerender(<PostersSidebar store={store2} dark={false} />);
    expect((screen.getByTestId("poster-undo") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId("poster-redo") as HTMLButtonElement).disabled).toBe(false);

    await user.click(screen.getByTestId("poster-undo"));
    expect(store2.undo).toHaveBeenCalledTimes(1);
    await user.click(screen.getByTestId("poster-redo"));
    expect(store2.redo).toHaveBeenCalledTimes(1);
  });
});

describe("PostersSidebar - 搜索过滤", () => {
  it("输入子串后只显示匹配的海报", async () => {
    const user = userEvent.setup();
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    const search = screen.getByTestId("poster-search-input");
    await user.type(search, "演唱");
    expect(screen.queryByText("已保存1")).toBeNull();
    expect(screen.queryByText("已保存2")).toBeNull();
    expect(screen.getByText("演唱回顾")).toBeTruthy();
  });

  it("大小写不敏感（中文不受影响，但 latin 字符小写也命中）", async () => {
    const store = makeFakeStore({
      posters: [
        { id: "p1", name: "Hello World", layout_id: "x", theme_id: "x",
          canvas_id: "x", created_at: "2026-07-30T00:00:00",
          updated_at: "2026-07-30T00:00:00", song_count: 1 },
        { id: "p2", name: "FOO", layout_id: "x", theme_id: "x",
          canvas_id: "x", created_at: "2026-07-30T00:00:00",
          updated_at: "2026-07-30T00:00:00", song_count: 1 },
      ],
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.type(screen.getByTestId("poster-search-input"), "hello");
    expect(screen.getByText("Hello World")).toBeTruthy();
    expect(screen.queryByText("FOO")).toBeNull();
  });

  it("空结果显示占位提示", async () => {
    const user = userEvent.setup();
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    await user.type(screen.getByTestId("poster-search-input"), "不存在的关键词");
    expect(screen.getByTestId("poster-empty")).toBeTruthy();
    expect(screen.getByTestId("poster-empty").textContent).toContain("没有匹配");
  });

  it("清空搜索恢复显示全部", async () => {
    const user = userEvent.setup();
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    const search = screen.getByTestId("poster-search-input");
    await user.type(search, "演唱");
    expect(screen.queryByText("已保存1")).toBeNull();
    await user.clear(search);
    expect(screen.getByText("已保存1")).toBeTruthy();
  });
});

describe("PostersSidebar - 排序", () => {
  it("默认 updated 模式", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    const sel = screen.getByTestId("poster-sort-select") as HTMLSelectElement;
    expect(sel.value).toBe("updated");
  });

  it("切换到 name 模式按名称 A-Z 排序（3 张均显示）", async () => {
    const user = userEvent.setup();
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    const sel = screen.getByTestId("poster-sort-select");
    await user.selectOptions(sel, "name");
    const items = screen.getAllByTestId(/^poster-item-/);
    expect(items.length).toBe(3);
  });

  it("切换到 songs 模式按歌数降序", async () => {
    const user = userEvent.setup();
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    await user.selectOptions(screen.getByTestId("poster-sort-select"), "songs");
    const items = screen.getAllByTestId(/^poster-item-/);
    // 演唱回顾(25) > 已保存1(12) > 已保存2(7)
    expect(items[0].textContent).toContain("×25");
    expect(items[1].textContent).toContain("×12");
    expect(items[2].textContent).toContain("×7");
  });
});

describe("PostersSidebar - 右键菜单", () => {
  // 事件挂在内层 <div role="button"> 上，所以从该 div 派发
  function getItemDiv(id: string): HTMLElement {
    return screen.getByTestId(`poster-item-${id}`).firstElementChild as HTMLElement;
  }
  function openContextMenu(id: string) {
    fireEvent.contextMenu(getItemDiv(id));
  }

  it("右键打开菜单（重命名/复制/删除）", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    openContextMenu("poster_1");
    expect(screen.getByTestId("poster-context-menu")).toBeTruthy();
    expect(screen.getByTestId("poster-context-rename")).toBeTruthy();
    expect(screen.getByTestId("poster-context-duplicate")).toBeTruthy();
    expect(screen.getByTestId("poster-context-delete")).toBeTruthy();
  });

  it("点击菜单外（document click）关闭菜单", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    openContextMenu("poster_1");
    expect(screen.getByTestId("poster-context-menu")).toBeTruthy();
    fireEvent.click(document.body);
    expect(screen.queryByTestId("poster-context-menu")).toBeNull();
  });

  it("Esc 关闭菜单", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    openContextMenu("poster_1");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("poster-context-menu")).toBeNull();
  });

  it("点击「重命名」进入 inline 编辑", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    openContextMenu("poster_1");
    fireEvent.click(screen.getByTestId("poster-context-rename"));
    const input = screen.getByTestId("poster-rename-input-poster_1");
    expect(input).toBeTruthy();
    expect((input as HTMLInputElement).value).toBe("已保存1");
  });

  it("点击「复制副本」调 store.duplicate（当前海报）", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    render(<PostersSidebar store={store} dark={false} />);
    openContextMenu("poster_1");
    fireEvent.click(screen.getByTestId("poster-context-duplicate"));
    await waitFor(() => expect(store.duplicate).toHaveBeenCalledTimes(1));
  });

  it("点击「复制副本」（非当前海报）走 select → duplicate → select 回原", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    render(<PostersSidebar store={store} dark={false} />);
    openContextMenu("poster_2");
    fireEvent.click(screen.getByTestId("poster-context-duplicate"));
    await waitFor(() => expect(store.duplicate).toHaveBeenCalledTimes(1));
    expect((store.select as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("点击「删除」调 window.confirm + select + deleteCurrent", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    render(<PostersSidebar store={store} dark={false} />);
    openContextMenu("poster_2");
    fireEvent.click(screen.getByTestId("poster-context-delete"));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect(store.deleteCurrent).toHaveBeenCalledTimes(1);
  });

  it("删除确认取消时不调 deleteCurrent", async () => {
    confirmSpy.mockReturnValue(false);
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    render(<PostersSidebar store={store} dark={false} />);
    openContextMenu("poster_2");
    fireEvent.click(screen.getByTestId("poster-context-delete"));
    expect(window.confirm).toHaveBeenCalled();
    expect(store.deleteCurrent).not.toHaveBeenCalled();
  });
});

describe("PostersSidebar - inline rename", () => {
  function getItemDiv(id: string): HTMLElement {
    return screen.getByTestId(`poster-item-${id}`).firstElementChild as HTMLElement;
  }

  it("双击名进入 inline 编辑", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    fireEvent.doubleClick(getItemDiv("poster_1"));
    expect(screen.getByTestId("poster-rename-input-poster_1")).toBeTruthy();
  });

  it("Enter 提交 → 当前海报走 store.rename", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    fireEvent.doubleClick(getItemDiv("poster_1"));
    const input = screen.getByTestId("poster-rename-input-poster_1");
    await user.clear(input);
    await user.type(input, "新名字{enter}");
    await waitFor(() => expect(store.rename).toHaveBeenCalledWith("新名字"));
  });

  it("失焦提交当前海报", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    fireEvent.doubleClick(getItemDiv("poster_1"));
    // 等 setTimeout(focus) 完成（startRename 内部 30ms 自动 focus）
    await new Promise((r) => setTimeout(r, 50));
    const input = screen.getByTestId("poster-rename-input-poster_1");
    await user.clear(input);
    await user.type(input, "失焦名字");
    fireEvent.blur(input);
    await waitFor(() => expect(store.rename).toHaveBeenCalledWith("失焦名字"), { timeout: 2000 });
  });

  it("Esc 取消不提交", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    fireEvent.doubleClick(getItemDiv("poster_1"));
    const input = screen.getByTestId("poster-rename-input-poster_1");
    await user.clear(input);
    await user.type(input, "不该提交的名字{escape}");
    expect(store.rename).not.toHaveBeenCalled();
    expect(screen.queryByTestId("poster-rename-input-poster_1")).toBeNull();
  });

  it("空名拒绝提交", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_1" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    fireEvent.doubleClick(getItemDiv("poster_1"));
    const input = screen.getByTestId("poster-rename-input-poster_1");
    await user.clear(input);
    await user.type(input, "  {enter}"); // 全是空格
    expect(store.rename).not.toHaveBeenCalled();
  });

  it("非当前海报重命名走独立 PATCH（不调 store.rename）", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_cur" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    fireEvent.doubleClick(getItemDiv("poster_1"));
    const input = screen.getByTestId("poster-rename-input-poster_1");
    await user.clear(input);
    await user.type(input, "新名字1{enter}");
    expect(store.rename).not.toHaveBeenCalled();
  });
});

describe("PostersSidebar - 缩略图", () => {
  it("渲染每个列表项的 <img> 指向 /api/posters/{id}/thumb", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    const img1 = screen.getByTestId("poster-thumb-poster_1") as HTMLImageElement;
    expect(img1.tagName).toBe("IMG");
    expect(img1.getAttribute("src")).toBe("/api/posters/poster_1/thumb");
    expect(img1.getAttribute("alt")).toBe("");
  });

  it("img 加载失败时 fallback 显示首字符", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    const img = screen.getByTestId("poster-thumb-poster_1") as HTMLImageElement;
    fireEvent.error(img);
    // fallback 是 img 的下一个兄弟 div，display 从 "none" 变 "flex"
    const fallback = img.nextElementSibling as HTMLElement;
    expect(fallback).toBeTruthy();
    expect(fallback.style.display).toBe("flex");
    expect(fallback.textContent).toBe("已"); // "已保存1" 的首字符
  });
});
