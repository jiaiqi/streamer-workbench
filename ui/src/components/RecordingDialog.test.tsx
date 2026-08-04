/// R8.2.x RecordingDialog 单元测试。
///
/// 覆盖：
/// - 浏览器模式：显示 unsupported 状态
/// - Electron 模式 idle：显示源选择 + 含音频 checkbox + 开始按钮
/// - 开始按钮触发 streamer.startRecording
/// - 录制中：显示红点 + 计时 + 暂停/停止
/// - 停止：调用 streamer.stopRecording + 切到 stopped 态列文件
/// - 错误态：显示 error 状态
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import RecordingDialog from "./RecordingDialog";
import { __resetRecordingStore } from "../hooks/useRecording";

const streamerMock = {
  listRecordingSources: vi.fn(),
  startRecording: vi.fn(),
  pauseRecording: vi.fn(),
  resumeRecording: vi.fn(),
  appendRecordingLrc: vi.fn(),
  stopRecording: vi.fn(),
  getRecordingState: vi.fn(),
  listRecordingFiles: vi.fn(),
  deleteRecording: vi.fn(),
  revealInFinder: vi.fn(),
};

vi.mock("../api/client", () => ({}));

vi.mock("../player/PlayerContext", () => ({
  usePlayer: () => ({
    currentSongId: null, mode: "browse", isPlaying: false, currentTimeMs: 0,
    setCurrent: vi.fn(), setMode: vi.fn(), setPlaying: vi.fn(), setCurrentTime: vi.fn(),
    lines: [],
  }),
}));

const toastMock = {
  success: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn(),
};
vi.mock("./Toast", () => ({
  ToastContext: { Provider: ({ children }: { children: React.ReactNode }) => children },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useToast: () => toastMock as any,
}));

beforeEach(() => {
  Object.values(streamerMock).forEach(fn => fn.mockReset());
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  toastMock.warn.mockReset();
  toastMock.info.mockReset();
  // 重置 module-level store（test 间状态隔离）
  __resetRecordingStore();
  // 默认浏览器模式
  (window as { streamer?: unknown }).streamer = undefined;
});

afterEach(() => cleanup());

function setStreamer() {
  (window as { streamer?: unknown }).streamer = streamerMock;
}

describe("RecordingDialog", () => {
  it("浏览器模式显示 unsupported", async () => {
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("recording-unsupported")).toBeTruthy();
    });
  });

  it("Electron 模式：默认显示 idle + 源选择", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: true,
      sources: [
        { id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null },
      ],
    });
    streamerMock.getRecordingState.mockResolvedValue({ ok: true, active: null });
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("recording-idle")).toBeTruthy();
    });
    expect(getByTestId("recording-source-select")).toBeTruthy();
    expect(getByTestId("recording-include-audio")).toBeTruthy();
    expect(getByTestId("recording-start-button")).toBeTruthy();
  });

  it("点开始按钮 → 调 streamer.startRecording", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: true,
      sources: [{ id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null }],
    });
    streamerMock.getRecordingState.mockResolvedValue({ ok: true, active: null });
    streamerMock.startRecording.mockResolvedValue({
      ok: true, id: "rec-1", startedAt: Date.now(), outputDir: "/tmp/r",
    });
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("recording-idle")).toBeTruthy());
    fireEvent.click(getByTestId("recording-start-button"));
    await waitFor(() => {
      expect(streamerMock.startRecording).toHaveBeenCalledWith(expect.objectContaining({
        sourceId: "screen:1",
        includeAudio: true,  // 默认勾上
      }));
    });
  });

  it("录制中：active 视图 + 暂停/停止按钮", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: true,
      sources: [{ id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null }],
    });
    // 挂载时已有活跃录制
    streamerMock.getRecordingState.mockResolvedValue({
      ok: true, id: "rec-1", status: "recording",
      startedAt: Date.now() - 10_000, elapsedMs: 10_000,
      totalBytes: 5000, segmentIndex: 0,
      files: [], sourceName: "S1", outputDir: "/tmp/r",
    });
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("recording-active")).toBeTruthy();
    });
    expect(getByTestId("recording-pause-button")).toBeTruthy();
    expect(getByTestId("recording-stop-button")).toBeTruthy();
  });

  it("点停止 → 调 streamer.stopRecording", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: true,
      sources: [{ id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null }],
    });
    streamerMock.getRecordingState.mockResolvedValue({
      ok: true, id: "rec-1", status: "recording",
      startedAt: Date.now() - 5_000, elapsedMs: 5_000,
      totalBytes: 1000, segmentIndex: 0,
      files: [], sourceName: "S1", outputDir: "/tmp/r",
    });
    streamerMock.stopRecording.mockResolvedValue({
      ok: true, id: "rec-1", durationMs: 5_000, outputDir: "/tmp/r",
      files: [{ name: "seg-000.webm", path: "/tmp/r/seg-000.webm",
                bytes: 1000, index: 0, isSrt: false }],
    });
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("recording-active")).toBeTruthy());
    fireEvent.click(getByTestId("recording-stop-button"));
    await waitFor(() => {
      expect(streamerMock.stopRecording).toHaveBeenCalledWith("rec-1");
    });
    await waitFor(() => {
      expect(getByTestId("recording-stopped")).toBeTruthy();
    });
  });

  it("完成态显示文件列表 + revealInFinder 按钮", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: true,
      sources: [{ id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null }],
    });
    streamerMock.getRecordingState.mockResolvedValue({
      ok: true, id: "rec-1", status: "recording",
      startedAt: Date.now() - 5_000, elapsedMs: 5_000,
      totalBytes: 0, segmentIndex: 0,
      files: [], sourceName: "S1", outputDir: "/tmp/r",
    });
    streamerMock.stopRecording.mockResolvedValue({
      ok: true, id: "rec-1", durationMs: 5_000, outputDir: "/tmp/r",
      files: [
        { name: "seg-000.webm", path: "/tmp/r/seg-000.webm",
          bytes: 1024, index: 0, isSrt: false },
        { name: "seg-000.srt", path: "/tmp/r/seg-000.srt",
          bytes: 256, index: -1, isSrt: true },
      ],
    });
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("recording-active")).toBeTruthy());
    fireEvent.click(getByTestId("recording-stop-button"));
    await waitFor(() => expect(getByTestId("recording-stopped")).toBeTruthy());
    expect(getByTestId("recording-file-seg-000.webm")).toBeTruthy();
    expect(getByTestId("recording-file-seg-000.srt")).toBeTruthy();
    fireEvent.click(getByTestId("recording-reveal-seg-000.webm"));
    expect(streamerMock.revealInFinder).toHaveBeenCalledWith({
      filePath: "/tmp/r/seg-000.webm",
    });
  });

  it("start 失败 → 显示 error 状态", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: true,
      sources: [{ id: "screen:1", name: "Entire Screen", isScreen: true, thumbnailDataUrl: null }],
    });
    streamerMock.getRecordingState.mockResolvedValue({ ok: true, active: null });
    streamerMock.startRecording.mockResolvedValue({
      ok: false, code: "permission_denied", error: "macOS 未授权",
    });
    const { getByTestId } = render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("recording-idle")).toBeTruthy());
    fireEvent.click(getByTestId("recording-start-button"));
    await waitFor(() => {
      expect(getByTestId("recording-error")).toBeTruthy();
    });
    expect(toastMock.error).toHaveBeenCalled();
  });

  it("列出源失败显示行内错误", async () => {
    setStreamer();
    streamerMock.listRecordingSources.mockResolvedValue({
      ok: false, code: "permission_denied", error: "需要屏幕录制权限",
    });
    streamerMock.getRecordingState.mockResolvedValue({ ok: true, active: null });
    render(
      <RecordingDialog open onClose={() => {}} />,
    );
    await waitFor(() => {
      expect(document.body.textContent ?? "").toContain("需要屏幕录制权限");
    });
  });

  it("open=false 不渲染 dialog content", () => {
    setStreamer();
    const { queryByTestId } = render(
      <RecordingDialog open={false} onClose={() => {}} />,
    );
    expect(queryByTestId("recording-dialog")).toBeNull();
  });
});
