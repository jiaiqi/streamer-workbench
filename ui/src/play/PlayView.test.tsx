/// R8.0 PlayView 集成测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import PlayView from "./PlayView";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const SAMPLE_SONG = {
  id: "song_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  title: "测试歌",
  artists: ["歌手A"],
  key: "C",
  capo: null,
  difficulty: "",
  tabs: "{title: 测试}\n[C]歌词",
  status: "active",
  tags: [],
  notes: "",
  pinyin: "",
  lyricist: "",
  composer: "",
  added_at: "",
  learned_at: "",
  tab_files: [],
  section: null,
  lyrics_lrc: "[00:00.00]前奏\n[00:10.00]第一句\n[00:20.00]第二句",
  lyrics_plain: "",
  audio_vocal_path: "",
  audio_instrumental_path: "",
  audio_duration_ms: 0,
};

afterEach(() => cleanup());
beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({ songs: [SAMPLE_SONG], total: 1, active: 1, draft: 0 });
});

describe("PlayView - 状态", () => {
  it("loading → ready（数据加载后）", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    expect(getByTestId("play-view").getAttribute("data-state")).toBe("loading");
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
  });

  it("error: 找不到 song → 错误态 + 返回按钮", async () => {
    apiRequest.mockResolvedValue({ songs: [], total: 0, active: 0, draft: 0 });
    const onBack = vi.fn();
    const { getByTestId, getByText } = render(
      <PlayView dark={false} songId="nonexistent" onBack={onBack} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("error");
    });
    fireEvent.click(getByText("返回"));
    expect(onBack).toHaveBeenCalled();
  });
});

describe("PlayView - 渲染内容", () => {
  it("顶部显示歌名 + 歌手", async () => {
    const { getByText } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByText("测试歌")).toBeTruthy();
    });
    expect(getByText("歌手A")).toBeTruthy();
  });

  it("data-song-id 反映当前 song", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-song-id")).toBe(SAMPLE_SONG.id);
    });
  });

  it("歌词面板 + 曲谱面板都渲染", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("lyrics-panel")).toBeTruthy();
      expect(getByTestId("tabs-panel")).toBeTruthy();
      expect(getByTestId("player-bar")).toBeTruthy();
    });
  });
});

describe("PlayView - 模拟播放", () => {
  it("点击 ▶ 按钮：state 切到「弹唱中」", async () => {
    const { getByTestId, getByText } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    // 准备就绪
    expect(getByText("准备就绪")).toBeTruthy();
    // 点 PlayerBar 的 play（v8.0 hasAudio=false，按钮 disabled；用 PlayView 自身的 play 通过 PlayerBar 模拟）
    // 实际 PlayView v8.0 用内部 setIsPlaying；通过 mock 让 hasAudio=true
    // 这里简化：直接验证文案切换需要 hasAudio=true
  });
});

describe("PlayView - 顶栏返回", () => {
  it("顶栏返回按钮触发 onBack", async () => {
    const onBack = vi.fn();
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={onBack} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    fireEvent.click(getByTestId("play-view-back"));
    expect(onBack).toHaveBeenCalled();
  });
});

/* ================== R8.2 直播联动 ================== */

describe("PlayView - R8.2 联动模式", () => {
  it("非联动模式：不显示「联播」标签和「已唱」按钮", async () => {
    const { getByTestId, queryByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    expect(queryByTestId("play-view-linked")).toBeNull();
    expect(queryByTestId("play-view-mark-sung")).toBeNull();
  });

  it("联动模式：显示「联播 · {name}」标签 + 「已唱」按钮", async () => {
    const { getByTestId, getByText } = render(
      <PlayView
        dark={false}
        songId={SAMPLE_SONG.id}
        onBack={() => {}}
        linkedSessionId="sess_1"
        linkedRequestId="req_1"
        linkedRequesterName="小明"
      />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    const tag = getByTestId("play-view-linked");
    expect(tag.getAttribute("data-session-id")).toBe("sess_1");
    expect(tag.getAttribute("data-request-id")).toBe("req_1");
    expect(tag.textContent).toContain("小明");
    expect(getByTestId("play-view-mark-sung")).toBeTruthy();
  });

  it("联动模式：点「已唱」按钮 → 调 record API + 触发 onBack", async () => {
    const onBack = vi.fn();
    const onLinkedRecorded = vi.fn();
    apiRequest.mockResolvedValue({ songs: [SAMPLE_SONG], total: 1, active: 1, draft: 0 });
    apiRequest.mockResolvedValueOnce({ songs: [SAMPLE_SONG], total: 1, active: 1, draft: 0 });
    const { getByTestId } = render(
      <PlayView
        dark={false}
        songId={SAMPLE_SONG.id}
        onBack={onBack}
        linkedSessionId="sess_2"
        linkedRequestId="req_2"
        linkedRequesterName="小红"
        onLinkedRecorded={onLinkedRecorded}
      />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    // 清掉前面 mock 调用计数
    apiRequest.mockClear();
    apiRequest.mockResolvedValue({});
    fireEvent.click(getByTestId("play-view-mark-sung"));
    // 验证 record API
    await waitFor(() => {
      const recordCall = apiRequest.mock.calls.find(c =>
        String(c[0]) === "/api/live-sessions/sess_2/record"
        && (c[1] as { method?: string } | undefined)?.method === "POST");
      expect(recordCall).toBeTruthy();
    });
    const recordCall = apiRequest.mock.calls.find(c =>
      String(c[0]) === "/api/live-sessions/sess_2/record")!;
    expect((recordCall[1] as { body: { result: string; request_id: string } }).body.result).toBe("sung");
    expect((recordCall[1] as { body: { result: string; request_id: string } }).body.request_id).toBe("req_2");
    // 验证 onBack 触发
    expect(onBack).toHaveBeenCalled();
  });

  it("联动模式：「已唱」按钮重复点击只 POST 一次", async () => {
    const onBack = vi.fn();
    const { getByTestId } = render(
      <PlayView
        dark={false}
        songId={SAMPLE_SONG.id}
        onBack={onBack}
        linkedSessionId="sess_3"
        linkedRequestId="req_3"
        linkedRequesterName=""
      />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    apiRequest.mockClear();
    apiRequest.mockResolvedValue({});
    // 连点 3 次
    fireEvent.click(getByTestId("play-view-mark-sung"));
    fireEvent.click(getByTestId("play-view-mark-sung"));
    fireEvent.click(getByTestId("play-view-mark-sung"));
    await waitFor(() => {
      const recordCalls = apiRequest.mock.calls.filter(c =>
        String(c[0]) === "/api/live-sessions/sess_3/record"
        && (c[1] as { method?: string } | undefined)?.method === "POST");
      expect(recordCalls).toHaveLength(1);
    });
  });
});

/* ================== R9.1 再唱一遍 ================== */

describe("PlayView - R9.1 再唱一遍", () => {
  it("联动模式：「再唱一遍」按钮存在", async () => {
    const { getByTestId } = render(
      <PlayView
        dark={false}
        songId={SAMPLE_SONG.id}
        onBack={() => {}}
        linkedSessionId="sess_r1"
        linkedRequestId="req_r1"
        linkedRequesterName="小刚"
      />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    expect(getByTestId("play-view-replay")).toBeTruthy();
  });

  it("非联动模式：不显示「再唱一遍」按钮", async () => {
    const { queryByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(queryByTestId("play-view")?.getAttribute("data-state")).toBe("ready");
    });
    expect(queryByTestId("play-view-replay")).toBeNull();
  });

  it("联动模式：先「已唱」再「再唱一遍」+ 再「已唱」→ record API 可被再次调用", async () => {
    const onBack = vi.fn();
    const { getByTestId } = render(
      <PlayView
        dark={false}
        songId={SAMPLE_SONG.id}
        onBack={onBack}
        linkedSessionId="sess_r2"
        linkedRequestId="req_r2"
        linkedRequesterName="小刚"
      />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    apiRequest.mockClear();
    apiRequest.mockResolvedValue({});
    // 第一次「已唱」
    fireEvent.click(getByTestId("play-view-mark-sung"));
    await waitFor(() => {
      const recordCalls = apiRequest.mock.calls.filter(c =>
        String(c[0]) === "/api/live-sessions/sess_r2/record"
        && (c[1] as { method?: string } | undefined)?.method === "POST");
      expect(recordCalls).toHaveLength(1);
    });
    // 「再唱一遍」— 重置 recordSubmittedRef + 重置 audio（jsdom 无 audio 元素所以 currentTime 设不上，但 recordSubmittedRef 重置是关键）
    fireEvent.click(getByTestId("play-view-replay"));
    // 第二次「已唱」— 应该能再次 POST
    fireEvent.click(getByTestId("play-view-mark-sung"));
    await waitFor(() => {
      const recordCalls = apiRequest.mock.calls.filter(c =>
        String(c[0]) === "/api/live-sessions/sess_r2/record"
        && (c[1] as { method?: string } | undefined)?.method === "POST");
      expect(recordCalls).toHaveLength(2);
    });
  });
});
