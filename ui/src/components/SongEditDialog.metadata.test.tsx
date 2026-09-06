/// M2.9 SongEditDialog 在线补全流程测试。
///
/// 覆盖：
/// - 按钮存在 + 默认 title 给到时可点击
/// - 离线时按钮 disabled
/// - title 为空时按钮 disabled
/// - 点击按钮 → 打开 MetadataSearchDialog
/// - 选中 hit → form.title / form.artists 填回
/// - notes 追加 [meta:source song_id=...] 行
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import SongEditDialog from "./SongEditDialog";
import { makeSong } from "../test-fixtures";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

vi.mock("./OnlineStatusBadge", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./OnlineStatusBadge")>();
  return {
    ...actual,
    getOnlineState: vi.fn(() => "online"),
  };
});

const SAMPLE = makeSong();

const SAMPLE_HIT = {
  source: "netease",
  song_id: "999",
  title: "七里香",
  artist: "周杰伦",
  album: "七里香",
  duration_ms: 234000,
  cover_url: "http://x/c.jpg",
};

const SAMPLE_DETAIL = {
  source: "netease",
  song_id: "999",
  title: "七里香",
  artist: "周杰伦",
  artist_id: "1",
  album: "七里香",
  album_id: "2",
  duration_ms: 234000,
  cover_url: "http://x/c.jpg",
  bpm: null,
};

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockImplementation((path: string) => {
    if (path === "/api/metadata/search") {
      return Promise.resolve({ keyword: "周杰伦", type: "song", provider: "netease", items: [SAMPLE_HIT] });
    }
    if (path === "/api/metadata/song") {
      return Promise.resolve(SAMPLE_DETAIL);
    }
    return Promise.resolve({});
  });
});
afterEach(() => cleanup());

describe("SongEditDialog - 在线补全（M2.9）", () => {
  it("有 title 时按钮可点击", () => {
    const { getByTestId } = render(
      <SongEditDialog target={SAMPLE} onClose={() => {}} onSaved={async () => {}} />,
    );
    const btn = getByTestId("metadata-button") as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.disabled).toBe(false);
  });

  it("title 为空时按钮 disabled", () => {
    const empty = { ...SAMPLE, title: "" };
    const { getByTestId } = render(
      <SongEditDialog target={empty} onClose={() => {}} onSaved={async () => {}} />,
    );
    const btn = getByTestId("metadata-button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("离线时按钮 disabled", async () => {
    const { getOnlineState } = await import("./OnlineStatusBadge");
    (getOnlineState as ReturnType<typeof vi.fn>).mockReturnValue("offline");
    const { getByTestId } = render(
      <SongEditDialog target={SAMPLE} onClose={() => {}} onSaved={async () => {}} />,
    );
    const btn = getByTestId("metadata-button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    // 恢复 online 避免影响其他测试
    (getOnlineState as ReturnType<typeof vi.fn>).mockReturnValue("online");
  });

  it("点击按钮 → 打开 MetadataSearchDialog", async () => {
    const { getByTestId } = render(
      <SongEditDialog target={SAMPLE} onClose={() => {}} onSaved={async () => {}} />,
    );
    fireEvent.click(getByTestId("metadata-button"));
    await waitFor(() => {
      expect(getByTestId("metadata-search-dialog")).toBeTruthy();
    });
  });

  it("选中 hit → form.title / form.artists 填回", async () => {
    const { getByTestId, getAllByTestId } = render(
      <SongEditDialog target={SAMPLE} onClose={() => {}} onSaved={async () => {}} />,
    );
    fireEvent.click(getByTestId("metadata-button"));
    await waitFor(() => {
      expect(getByTestId("metadata-search-dialog")).toBeTruthy();
    });
    await waitFor(() => {
      expect(getAllByTestId("hit-item")).toHaveLength(1);
    });
    fireEvent.click(getAllByTestId("hit-item")[0]);
    await waitFor(() => {
      // form.title 应被更新
      const titleInput = document.querySelector("#song-title") as HTMLInputElement;
      expect(titleInput.value).toBe("七里香");
      // form.artists 应被更新
      const artistInput = document.querySelector("#song-artists") as HTMLInputElement;
      expect(artistInput.value).toBe("周杰伦");
    });
  });

  it("选中后 notes 追加 [meta:netease song_id=...]", async () => {
    const { getByTestId, getAllByTestId } = render(
      <SongEditDialog target={SAMPLE} onClose={() => {}} onSaved={async () => {}} />,
    );
    fireEvent.click(getByTestId("metadata-button"));
    await waitFor(() => expect(getByTestId("metadata-search-dialog")).toBeTruthy());
    await waitFor(() => expect(getAllByTestId("hit-item")).toHaveLength(1));
    fireEvent.click(getAllByTestId("hit-item")[0]);
    await waitFor(() => {
      const notes = document.querySelector("#song-notes") as HTMLTextAreaElement;
      expect(notes.value).toMatch(/\[meta:netease song_id=999/);
    });
  });

  it("多歌手 'A / B' → 表单用逗号分隔", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/metadata/search") {
        return Promise.resolve({
          keyword: "x", type: "song", provider: "netease",
          items: [{ ...SAMPLE_HIT, song_id: "888", title: "合唱", artist: "A / B" }],
        });
      }
      if (path === "/api/metadata/song") {
        return Promise.resolve({ ...SAMPLE_DETAIL, song_id: "888", title: "合唱", artist: "A / B" });
      }
      return Promise.resolve({});
    });
    const { getByTestId, getAllByTestId } = render(
      <SongEditDialog target={SAMPLE} onClose={() => {}} onSaved={async () => {}} />,
    );
    fireEvent.click(getByTestId("metadata-button"));
    await waitFor(() => expect(getAllByTestId("hit-item")).toHaveLength(1));
    fireEvent.click(getAllByTestId("hit-item")[0]);
    await waitFor(() => {
      const artistInput = document.querySelector("#song-artists") as HTMLInputElement;
      expect(artistInput.value).toBe("A，B");
    });
  });

  it("已有 notes 时新 meta 行追加（不覆盖）", async () => {
    const withNotes = { ...SAMPLE, notes: "副歌高音要降 key" };
    const { getByTestId, getAllByTestId } = render(
      <SongEditDialog target={withNotes} onClose={() => {}} onSaved={async () => {}} />,
    );
    fireEvent.click(getByTestId("metadata-button"));
    await waitFor(() => expect(getAllByTestId("hit-item")).toHaveLength(1));
    fireEvent.click(getAllByTestId("hit-item")[0]);
    await waitFor(() => {
      const notes = document.querySelector("#song-notes") as HTMLTextAreaElement;
      expect(notes.value).toContain("副歌高音要降 key");
      expect(notes.value).toContain("[meta:netease song_id=999");
    });
  });
});
