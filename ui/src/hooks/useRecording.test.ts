/// R8.2.x useRecording hook 单元测试。
///
/// 覆盖：
/// - 格式化函数：formatElapsed / formatBytes
/// - module-level store 共享 state（两个 hook 实例同步）
/// - 浏览器模式：useRecording 设置 status="unsupported"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, act } from "@testing-library/react";
import { formatElapsed, formatBytes, useRecording, useRecordingIndicator } from "./useRecording";

// mock PlayerContext（useRecording 内部依赖）
vi.mock("../player/PlayerContext", () => ({
  usePlayer: () => ({
    currentSongId: null, mode: "browse", isPlaying: false, currentTimeMs: 0,
    setCurrent: vi.fn(), setMode: vi.fn(), setPlaying: vi.fn(), setCurrentTime: vi.fn(),
    lines: [],
  }),
}));

beforeEach(() => {
  cleanup();
  // 默认：不在 Electron
  (window as { streamer?: unknown }).streamer = undefined;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("formatElapsed", () => {
  it("0 ms → 00:00", () => expect(formatElapsed(0)).toBe("00:00"));
  it("sub-second 截断", () => expect(formatElapsed(500)).toBe("00:00"));
  it("59.5s → 00:59", () => expect(formatElapsed(59_500)).toBe("00:59"));
  it("60s → 01:00", () => expect(formatElapsed(60_000)).toBe("01:00"));
  it("1h 23m 45s → 1:23:45", () =>
    expect(formatElapsed(5_025_000)).toBe("1:23:45"));
});

describe("formatBytes", () => {
  it("B", () => expect(formatBytes(512)).toBe("512 B"));
  it("KB", () => expect(formatBytes(2048)).toBe("2.0 KB"));
  it("MB", () => expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB"));
  it("GB", () => expect(formatBytes(2 * 1024 * 1024 * 1024)).toBe("2.00 GB"));
});

describe("useRecordingIndicator 静态只读", () => {
  it("浏览器模式：isElectron=false, status=unsupported", () => {
    const { result } = renderHook(() => useRecordingIndicator());
    expect(result.current.isElectron).toBe(false);
    // store 自动切到 unsupported（不依赖 useEffect）
    expect(result.current.status).toBe("unsupported");
  });
  it("Electron 模式：isElectron=true", () => {
    (window as { streamer?: unknown }).streamer = {
      listRecordingSources: vi.fn(),
      startRecording: vi.fn(),
      pauseRecording: vi.fn(),
      resumeRecording: vi.fn(),
      appendRecordingLrc: vi.fn(),
      stopRecording: vi.fn(),
      getRecordingState: vi.fn().mockResolvedValue({ ok: true, active: null }),
      listRecordingFiles: vi.fn(),
      deleteRecording: vi.fn(),
    };
    const { result } = renderHook(() => useRecordingIndicator());
    expect(result.current.isElectron).toBe(true);
  });
});

describe("useRecording 浏览器模式", () => {
  it("设置 status='unsupported'", async () => {
    const { result } = renderHook(() => useRecording());
    await act(async () => {
      await new Promise(r => setTimeout(r, 10));
    });
    expect(result.current.status).toBe("unsupported");
  });
});

describe("useRecording Electron 模式 + module store 共享", () => {
  const mockStreamer = () => {
    (window as { streamer?: unknown }).streamer = {
      listRecordingSources: vi.fn().mockResolvedValue({
        ok: true, sources: [
          { id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null },
        ],
      }),
      startRecording: vi.fn().mockResolvedValue({ ok: true, id: "rec-1",
        startedAt: Date.now(), outputDir: "/tmp/r" }),
      pauseRecording: vi.fn().mockResolvedValue({ ok: true, status: "paused" }),
      resumeRecording: vi.fn().mockResolvedValue({ ok: true, status: "recording" }),
      appendRecordingLrc: vi.fn().mockResolvedValue({ ok: true, count: 1 }),
      stopRecording: vi.fn().mockResolvedValue({
        ok: true, id: "rec-1", durationMs: 5000, outputDir: "/tmp/r",
        files: [{ name: "seg-000.webm", path: "/tmp/r/seg-000.webm",
                  bytes: 1000, index: 0, isSrt: false }],
      }),
      getRecordingState: vi.fn().mockResolvedValue({ ok: true, active: null }),
      listRecordingFiles: vi.fn().mockResolvedValue({ ok: true, dir: "/tmp/r", files: [] }),
      deleteRecording: vi.fn().mockResolvedValue({ ok: true, deleted: 0 }),
    };
  };

  it("start → store 状态切到 recording", async () => {
    mockStreamer();
    const { result } = renderHook(() => useRecording());
    await act(async () => {
      await result.current.start({
        sourceId: "screen:1", includeAudio: true, sourceName: "Entire Screen",
      });
    });
    expect(result.current.status).toBe("recording");
    expect(result.current.id).toBe("rec-1");
  });

  it("两个 hook 实例共享 store：indicator 跟随 recording 变化", async () => {
    mockStreamer();
    const a = renderHook(() => useRecording());
    const b = renderHook(() => useRecordingIndicator());
    await act(async () => {
      await a.result.current.start({
        sourceId: "screen:1", includeAudio: false, sourceName: "S1",
      });
    });
    // 同步：indicator 看到 status=recording
    expect(a.result.current.status).toBe("recording");
    expect(b.result.current.status).toBe("recording");
  });

  it("stop → 状态切到 stopped + 返回 files", async () => {
    mockStreamer();
    const { result } = renderHook(() => useRecording());
    await act(async () => {
      await result.current.start({
        sourceId: "screen:1", includeAudio: true, sourceName: "S1",
      });
    });
    let files: { name: string; path: string; bytes: number;
      index: number; isSrt: boolean }[] = [];
    await act(async () => {
      files = await result.current.stop();
    });
    expect(result.current.status).toBe("stopped");
    expect(files.length).toBe(1);
    expect(files[0].name).toBe("seg-000.webm");
  });

  it("pause → 状态切到 paused", async () => {
    mockStreamer();
    const { result } = renderHook(() => useRecording());
    await act(async () => {
      await result.current.start({
        sourceId: "screen:1", includeAudio: false, sourceName: "S1",
      });
    });
    await act(async () => { await result.current.pause(); });
    expect(result.current.status).toBe("paused");
    await act(async () => { await result.current.resume(); });
    expect(result.current.status).toBe("recording");
  });

  it("start 失败 → 状态切到 error", async () => {
    (window as { streamer?: unknown }).streamer = {
      listRecordingSources: vi.fn().mockResolvedValue({ ok: true, sources: [] }),
      startRecording: vi.fn().mockResolvedValue({
        ok: false, code: "permission_denied", error: "macOS 未授权屏幕录制",
      }),
      pauseRecording: vi.fn(),
      resumeRecording: vi.fn(),
      appendRecordingLrc: vi.fn(),
      stopRecording: vi.fn(),
      getRecordingState: vi.fn().mockResolvedValue({ ok: true, active: null }),
      listRecordingFiles: vi.fn(),
      deleteRecording: vi.fn(),
    };
    const { result } = renderHook(() => useRecording());
    let success = true;
    await act(async () => {
      success = await result.current.start({
        sourceId: "screen:1", includeAudio: false,
      });
    });
    expect(success).toBe(false);
    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toContain("permission_denied");
  });

  it("reset 清除 store 状态", async () => {
    mockStreamer();
    const { result } = renderHook(() => useRecording());
    await act(async () => {
      await result.current.start({ sourceId: "screen:1", includeAudio: false });
    });
    expect(result.current.status).toBe("recording");
    act(() => { result.current.reset(); });
    expect(result.current.status).toBe("idle");
  });

  it("refreshSources 拉源列表", async () => {
    mockStreamer();
    const { result } = renderHook(() => useRecording());
    await act(async () => {
      await result.current.refreshSources();
    });
    expect(result.current.sources.length).toBe(1);
    expect(result.current.sources[0].isScreen).toBe(true);
  });
});

