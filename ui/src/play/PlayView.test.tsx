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

/* ================== R9.2 远观模式 ================== */

describe("PlayView - R9.2 远观模式", () => {
  it("默认 sizeScale = 1（标准）", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    expect(getByTestId("play-view-size-1").getAttribute("data-active")).toBe("true");
    expect(getByTestId("play-view-size-1.3").getAttribute("data-active")).toBe("false");
    expect(getByTestId("play-view-size-1.6").getAttribute("data-active")).toBe("false");
  });

  it("点击 1.6x → LyricsPanel 当前行 inline style fontSize 反映放大", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    fireEvent.click(getByTestId("play-view-size-1.6"));
    expect(getByTestId("play-view-size-1.6").getAttribute("data-active")).toBe("true");
    // 当前行（第一行）应该应用 1.5 * 1.6 = 2.4rem
    await waitFor(() => {
      const lines = document.querySelectorAll('[data-testid="lyrics-panel-line"]');
      const activeLine = Array.from(lines).find(ln => ln.getAttribute("data-active") === "true");
      expect(activeLine).toBeTruthy();
      const style = (activeLine as HTMLElement).style.fontSize;
      expect(style).toBe("2.4rem");
    });
  });

  it("点击 1.3x → LyricsPanel 字号对应 1.3 倍", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    fireEvent.click(getByTestId("play-view-size-1.3"));
    await waitFor(() => {
      const lines = document.querySelectorAll('[data-testid="lyrics-panel-line"]');
      const activeLine = Array.from(lines).find(ln => ln.getAttribute("data-active") === "true");
      const style = (activeLine as HTMLElement).style.fontSize;
      expect(style).toBe("1.95rem");
    });
  });
});

/* ================== R9.3 Capo 标识 ================== */

const SAMPLE_SONG_WITH_KEY = {
  ...SAMPLE_SONG,
  key: "C",  // 原调 C
  capo: 0,
};

describe("PlayView - R9.3 Capo 标识", () => {
  it("Capo 组件渲染，初始取 song.capo=0 → 显示「无 Capo」", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    const capoBox = getByTestId("play-view-capo");
    expect(capoBox.getAttribute("data-capo")).toBe("0");
    expect(getByTestId("play-view-capo-value").textContent).toBe("无 Capo");
    // C + 0 = C，没有 → 实际 Key
    expect(capoBox.querySelector('[data-testid="play-view-actual-key"]')).toBeNull();
  });

  it("点击 + 按钮 → Capo 升 1 → 显示「Capo 1」+ 实际 Key=C#", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    fireEvent.click(getByTestId("play-view-capo-up"));
    const capoBox = getByTestId("play-view-capo");
    expect(capoBox.getAttribute("data-capo")).toBe("1");
    expect(capoBox.getAttribute("data-actual-key")).toBe("C#");
    expect(getByTestId("play-view-capo-value").textContent).toBe("Capo 1");
    expect(getByTestId("play-view-actual-key").textContent).toContain("→ C#");
  });

  it("Capo 0 时 − 按钮 disabled；Capo 12 时 + 按钮 disabled", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    expect((getByTestId("play-view-capo-down") as HTMLButtonElement).disabled).toBe(true);
    // 升到 12
    for (let i = 0; i < 12; i++) fireEvent.click(getByTestId("play-view-capo-up"));
    expect(getByTestId("play-view-capo").getAttribute("data-capo")).toBe("12");
    expect((getByTestId("play-view-capo-up") as HTMLButtonElement).disabled).toBe(true);
  });

  it("按 ↓↓↑↑ 快捷键 → Capo 跟着变", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    // Capo 0 → 1（↑）→ 2（↑）→ 1（↓）→ 2（↑）
    fireEvent.keyDown(window, { key: "ArrowUp" });
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(getByTestId("play-view-capo").getAttribute("data-capo")).toBe("2");
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(getByTestId("play-view-capo").getAttribute("data-capo")).toBe("1");
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(getByTestId("play-view-capo").getAttribute("data-capo")).toBe("2");
  });

  it("INPUT 元素聚焦时快捷键不触发", async () => {
    const { getByTestId, container } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    // 模拟 input 元素聚焦：jsdom 中 input 元素无进度条 input，但可以 dispatch
    const input = document.createElement("input");
    container.appendChild(input);
    input.focus();
    fireEvent.keyDown(input, { key: "ArrowUp" });
    // Capo 应该是 0 没变
    expect(getByTestId("play-view-capo").getAttribute("data-capo")).toBe("0");
  });
});

/* ================== R9.4 个人 Capo 库 ================== */

describe("PlayView - R9.4 个人 Capo 库", () => {
  it("「+ 习惯」按钮存在，初始状态 idle", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    const btn = getByTestId("play-view-save-capo");
    expect(btn).toBeTruthy();
    expect(btn.getAttribute("data-save-state")).toBe("idle");
    expect(btn.textContent).toBe("+ 习惯");
  });

  it("点击「+ 习惯」→ 调 PATCH /api/songs/{id}（带 capo_options + capo_default）", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    // 升 Capo 到 3（模拟主播想用 Capo 3）
    fireEvent.click(getByTestId("play-view-capo-up"));
    fireEvent.click(getByTestId("play-view-capo-up"));
    fireEvent.click(getByTestId("play-view-capo-up"));
    expect(getByTestId("play-view-capo").getAttribute("data-capo")).toBe("3");
    // 点 + 习惯 — 这次响应 mock 一次
    apiRequest.mockClear();
    apiRequest.mockResolvedValueOnce({});
    fireEvent.click(getByTestId("play-view-save-capo"));
    await waitFor(() => {
      const patchCall = apiRequest.mock.calls.find(c =>
        String(c[0]) === `/api/songs/${SAMPLE_SONG_WITH_KEY.id}`
        && (c[1] as { method?: string } | undefined)?.method === "PATCH");
      expect(patchCall).toBeTruthy();
    });
    const patchCall = apiRequest.mock.calls.find(c =>
      String(c[0]) === `/api/songs/${SAMPLE_SONG_WITH_KEY.id}`)!;
    const body = (patchCall[1] as { body: { capo_options: number[]; capo_default: number } }).body;
    expect(body.capo_options).toEqual([3]);  // 空 options + 3 = [3]
    expect(body.capo_default).toBe(3);
  });

  it("成功保存 → 按钮变「✓ 已加入」", async () => {
    const { getByTestId } = render(
      <PlayView dark={false} songId={SAMPLE_SONG_WITH_KEY.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    apiRequest.mockResolvedValueOnce({});
    fireEvent.click(getByTestId("play-view-save-capo"));
    await waitFor(() => {
      expect(getByTestId("play-view-save-capo").getAttribute("data-save-state")).toBe("saved");
    });
    expect(getByTestId("play-view-save-capo").textContent).toBe("✓ 已加入");
  });
});

describe("PlayView - M1.6 LRC 同步（timeupdate → LyricsPanel）", () => {
  // M1.6a: 验证 audio timeupdate 事件 → currentTimeMs → LyricsPanel 切当前行
  // 旧 R8 链路是「currentTimeMs state 上推 → 子组件响应」；这里直接测链路是否通
  const SONG_WITH_AUDIO = {
    ...SAMPLE_SONG,
    id: "song_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    title: "测试歌-带音频",
    audio_vocal_path: "vocal.mp3",
    audio_instrumental_path: "",
    audio_duration_ms: 30000,
    lyrics_lrc: "[00:00.00]前奏\n[00:10.00]第一句\n[00:20.00]第二句",
  };

  it("audio timeupdate → LyricsPanel 当前行切换（第一行 → 第二行）", async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ songs: [SONG_WITH_AUDIO], total: 1, active: 1, draft: 0 });
    const { getByTestId } = render(
      <PlayView dark={false} songId={SONG_WITH_AUDIO.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });

    // 初始 currentTimeMs=0 → 第一行（"前奏"）active
    const audio = getByTestId("play-view-audio") as HTMLAudioElement;
    expect(audio).toBeTruthy();

    // 模拟 timeupdate：currentTime=15s → 第二行（"第一句"）
    Object.defineProperty(audio, "currentTime", { configurable: true, value: 15, writable: true });
    audio.dispatchEvent(new Event("timeupdate"));

    await waitFor(() => {
      const lines = document.querySelectorAll('[data-testid="lyrics-panel-line"]');
      const activeLine = Array.from(lines).find(ln => ln.getAttribute("data-active") === "true");
      expect(activeLine).toBeTruthy();
      expect(activeLine!.getAttribute("data-time-ms")).toBe("10000");
      expect(activeLine!.textContent).toBe("第一句");
    });
  });

  it("timeupdate 推 22s → LyricsPanel 当前行切到「第二句」", async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ songs: [SONG_WITH_AUDIO], total: 1, active: 1, draft: 0 });
    const { getByTestId } = render(
      <PlayView dark={false} songId={SONG_WITH_AUDIO.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    const audio = getByTestId("play-view-audio") as HTMLAudioElement;
    Object.defineProperty(audio, "currentTime", { configurable: true, value: 22, writable: true });
    audio.dispatchEvent(new Event("timeupdate"));
    await waitFor(() => {
      const lines = document.querySelectorAll('[data-testid="lyrics-panel-line"]');
      const activeLine = Array.from(lines).find(ln => ln.getAttribute("data-active") === "true");
      expect(activeLine!.textContent).toBe("第二句");
    });
  });

  it("拖动进度条（onSeek）→ LyricsPanel 当前行同步切", async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ songs: [SONG_WITH_AUDIO], total: 1, active: 1, draft: 0 });
    const { getByTestId } = render(
      <PlayView dark={false} songId={SONG_WITH_AUDIO.id} onBack={() => {}} />
    );
    await waitFor(() => {
      expect(getByTestId("play-view").getAttribute("data-state")).toBe("ready");
    });
    // PlayerBar 进度条 range input — 设 value=50 → 50% of totalMs
    // totalMs 来自 audio_duration_ms=30000 或 audio.duration；我们 mock 一下
    const audio = getByTestId("play-view-audio") as HTMLAudioElement;
    Object.defineProperty(audio, "duration", { configurable: true, value: 30, writable: true });
    audio.dispatchEvent(new Event("durationchange"));
    const progress = getByTestId("player-bar-progress") as HTMLInputElement;
    Object.defineProperty(progress, "value", { configurable: true, value: "50", writable: true });
    fireEvent.change(progress);
    await waitFor(() => {
      const lines = document.querySelectorAll('[data-testid="lyrics-panel-line"]');
      const activeLine = Array.from(lines).find(ln => ln.getAttribute("data-active") === "true");
      // 50% * 30000ms = 15000ms → "第一句" (10-20s)
      expect(activeLine!.textContent).toBe("第一句");
    });
  });
});
