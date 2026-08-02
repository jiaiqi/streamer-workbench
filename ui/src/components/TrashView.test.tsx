/// R9.6 TrashView 测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import TrashView from "./TrashView";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const SONGS = [
  { id: "song_a", title: "江南", artists: ["林俊杰"], status: "active",
    deleted_at: "2026-08-01T10:00:00Z" },
  { id: "song_b", title: "十年", artists: ["陈奕迅"], status: "active",
    deleted_at: "2026-07-15T08:00:00Z" },
];

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({});
});
afterEach(() => cleanup());

describe("TrashView", () => {
  it("加载垃圾桶歌曲列表", async () => {
    apiRequest.mockResolvedValueOnce({ songs: SONGS });
    const { getAllByTestId } = render(
      <TrashView dark={false} onChanged={() => {}} />
    );
    await waitFor(() => {
      const items = getAllByTestId("trash-item");
      expect(items.length).toBe(2);
    });
    // 验证 data-song-id 反映
    const a = document.querySelector('[data-testid="trash-item"][data-song-id="song_a"]');
    const b = document.querySelector('[data-testid="trash-item"][data-song-id="song_b"]');
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
  });

  it("垃圾桶空态", async () => {
    apiRequest.mockResolvedValueOnce({ songs: [] });
    const { getByText } = render(<TrashView dark={false} onChanged={() => {}} />);
    await waitFor(() => {
      expect(getByText(/垃圾桶是空的/)).toBeTruthy();
    });
  });

  it("点恢复 → 调 POST /api/songs/{id}/restore + 通知 onChanged", async () => {
    apiRequest.mockResolvedValueOnce({ songs: SONGS });
    apiRequest.mockResolvedValueOnce({ ok: true });
    const onChanged = vi.fn();
    const { getAllByTestId } = render(
      <TrashView dark={false} onChanged={onChanged} />
    );
    await waitFor(() => {
      expect(getAllByTestId("trash-item").length).toBe(2);
    });
    apiRequest.mockClear();
    apiRequest.mockResolvedValue({});
    const restoreBtns = getAllByTestId("trash-restore");
    fireEvent.click(restoreBtns[0]);
    await waitFor(() => {
      const restoreCall = apiRequest.mock.calls.find(c =>
        String(c[0]) === "/api/songs/song_a/restore"
        && (c[1] as { method?: string } | undefined)?.method === "POST");
      expect(restoreCall).toBeTruthy();
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it("点永久删除 → 调 DELETE /api/songs/{id}?permanent=true", async () => {
    apiRequest.mockResolvedValueOnce({ songs: SONGS });
    apiRequest.mockResolvedValueOnce({ ok: true });
    // 确认对话框
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onChanged = vi.fn();
    const { getAllByTestId } = render(
      <TrashView dark={false} onChanged={onChanged} />
    );
    await waitFor(() => {
      expect(getAllByTestId("trash-item").length).toBe(2);
    });
    apiRequest.mockClear();
    apiRequest.mockResolvedValue({});
    const purgeBtns = getAllByTestId("trash-purge");
    fireEvent.click(purgeBtns[0]);
    await waitFor(() => {
      const purgeCall = apiRequest.mock.calls.find(c =>
        String(c[0]).startsWith("/api/songs/song_a?permanent=true")
        && (c[1] as { method?: string } | undefined)?.method === "DELETE");
      expect(purgeCall).toBeTruthy();
    });
    expect(onChanged).toHaveBeenCalled();
  });
});
