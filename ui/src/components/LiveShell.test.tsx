/// P1-A3.1 LiveShell 总闸测试
///
/// 5 个核心场景覆盖（task 验收 §4）：
///   1. 无 active session：显示「暂无场次」+ 3 个动作按钮全部可点
///   2. active session + 不在弹唱：session 摘要 + 弹唱屏按钮可点 + 无联动徽标
///   3. 在弹唱 + 无联动：playMode 高亮 + 「关闭联动」按钮不显示
///   4. 在弹唱 + 联动：playMode 高亮 + 「🔗 联动中 · 小明 · 关闭」红色徽标
///   5. 点「主控制台」按钮：onOpenLiveView 被调
///
/// LiveShell 本身不调 API；所有 prop 由调用方注入；测试不 mock apiRequest。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import LiveShell from "./LiveShell";
import type { LiveShellProps } from "./LiveShell";

afterEach(() => cleanup());

/** 工具：构造默认 props，覆盖后返回新对象。 */
function makeProps(overrides: Partial<LiveShellProps> = {}): LiveShellProps {
  return {
    dark: false,
    activeSessionId: null,
    activeSessionTitle: null,
    queueSize: 0,
    isInPlayMode: false,
    isPlayLinked: false,
    playLinkInfo: null,
    onOpenLiveView: vi.fn(),
    onOpenQuickView: vi.fn(),
    onOpenPlayView: vi.fn(),
    onClosePlay: vi.fn(),
    ...overrides,
  };
}

describe("LiveShell 总闸", () => {
  it("场景 1: 无 active session — 显示「暂无场次」+ 3 个动作按钮全部可点", () => {
    const props = makeProps();
    const { getByTestId, queryByTestId } = render(<LiveShell {...props} />);

    // 位置指示：主控制台（默认不在弹唱）
    expect(getByTestId("live-shell-pos-live").textContent).toBe("主控制台");
    expect(queryByTestId("live-shell-pos-play")).toBeNull();

    // 暂无场次文案
    expect(getByTestId("live-shell-empty").textContent).toContain("暂无场次");
    expect(queryByTestId("live-shell-session")).toBeNull();

    // 3 个动作按钮全部可点
    const btnLive = getByTestId("live-shell-btn-live") as HTMLButtonElement;
    const btnQuick = getByTestId("live-shell-btn-quick") as HTMLButtonElement;
    const btnPlay = getByTestId("live-shell-btn-play") as HTMLButtonElement;
    expect(btnLive.disabled).toBe(false);
    expect(btnPlay.disabled).toBe(false);
    // 浏览器模式：isElectron() = false → 速查 disabled
    expect(btnQuick.disabled).toBe(true);
    expect(btnQuick.title).toBe("仅 Electron 桌面端支持");
  });

  it("场景 2: active session + 不在弹唱 — session 摘要正确 + 弹唱屏可点 + 无联动徽标", () => {
    const props = makeProps({
      activeSessionId: "sess_20260823_abc",
      activeSessionTitle: "今晚第 8 场",
      queueSize: 5,
    });
    const { getByTestId, queryByTestId } = render(<LiveShell {...props} />);

    // session 摘要：标题 + 队列徽标
    const title = getByTestId("live-shell-session-title");
    expect(title.textContent).toBe("今晚第 8 场");
    expect(getByTestId("live-shell-queue-badge").textContent).toContain("队列 5");

    // 不在弹唱 → 位置指示是「主控制台」，无联动徽标
    expect(getByTestId("live-shell-pos-live").textContent).toBe("主控制台");
    expect(queryByTestId("live-shell-link-badge")).toBeNull();
    expect(queryByTestId("live-shell-link-close")).toBeNull();
  });

  it("场景 3: 在弹唱 + 无联动 — playMode 高亮 + 关闭联动按钮不显示", () => {
    const props = makeProps({
      isInPlayMode: true,
      isPlayLinked: false,
    });
    const { getByTestId, queryByTestId } = render(<LiveShell {...props} />);

    // 位置指示：弹唱屏
    expect(getByTestId("live-shell-pos-play").textContent).toBe("弹唱屏");
    expect(queryByTestId("live-shell-pos-live")).toBeNull();

    // 弹唱屏按钮高亮：emerald 类
    const btnPlay = getByTestId("live-shell-btn-play") as HTMLButtonElement;
    expect(btnPlay.className).toContain("bg-emerald-500");

    // 无联动 → 联动徽标不显示
    expect(queryByTestId("live-shell-link-badge")).toBeNull();
    expect(queryByTestId("live-shell-link-close")).toBeNull();
  });

  it("场景 4: 在弹唱 + 联动 — 红色联动徽标显示 + 含点歌人姓名", () => {
    const props = makeProps({
      isInPlayMode: true,
      isPlayLinked: true,
      playLinkInfo: {
        sessionId: "sess_20260823_abc",
        requestId: "req_xyz",
        requesterName: "小明",
        songId: "song_001",
      },
    });
    const { getByTestId } = render(<LiveShell {...props} />);

    // 位置指示：弹唱屏
    expect(getByTestId("live-shell-pos-play").textContent).toBe("弹唱屏");

    // 联动徽标存在 + 含点歌人姓名 + 关闭按钮
    const badge = getByTestId("live-shell-link-badge");
    expect(badge).toBeTruthy();
    expect(badge.textContent).toContain("联动中");
    expect(badge.textContent).toContain("小明");
    // 红色类（rose）
    expect(badge.className).toContain("rose");
    // 关闭按钮存在
    expect(getByTestId("live-shell-link-close")).toBeTruthy();
  });

  it("场景 5: 点「主控制台」按钮 — onOpenLiveView 被调一次", () => {
    const onOpenLiveView = vi.fn();
    const props = makeProps({ onOpenLiveView });
    const { getByTestId } = render(<LiveShell {...props} />);

    fireEvent.click(getByTestId("live-shell-btn-live"));
    expect(onOpenLiveView).toHaveBeenCalledTimes(1);
  });

  // ===== 额外覆盖（让组件测试更稳）=====

  it("点「弹唱屏」按钮 — onOpenPlayView 被调（不带 linked）", () => {
    const onOpenPlayView = vi.fn();
    const props = makeProps({ onOpenPlayView });
    const { getByTestId } = render(<LiveShell {...props} />);

    fireEvent.click(getByTestId("live-shell-btn-play"));
    expect(onOpenPlayView).toHaveBeenCalledTimes(1);
    // 调时未传参（无联动）
    expect(onOpenPlayView.mock.calls[0].length).toBe(0);
  });

  it("点「关闭联动」按钮 — onClosePlay 被调一次", () => {
    const onClosePlay = vi.fn();
    const props = makeProps({
      isInPlayMode: true,
      isPlayLinked: true,
      playLinkInfo: {
        sessionId: "s",
        requestId: "r",
        requesterName: "测试人",
        songId: "song",
      },
      onClosePlay,
    });
    const { getByTestId } = render(<LiveShell {...props} />);

    fireEvent.click(getByTestId("live-shell-link-close"));
    expect(onClosePlay).toHaveBeenCalledTimes(1);
  });

  it("activeSessionTitle 为空时回退显示「会话 + id 前 8 位」", () => {
    const props = makeProps({
      activeSessionId: "abcdef1234567890",
      activeSessionTitle: "",
      queueSize: 2,
    });
    const { getByTestId } = render(<LiveShell {...props} />);

    const title = getByTestId("live-shell-session-title");
    expect(title.textContent).toContain("会话");
    expect(title.textContent).toContain("abcdef12");
    expect(getByTestId("live-shell-queue-badge").textContent).toContain("队列 2");
  });

  it("dark 模式：根元素类含 bg-zinc-900/90", () => {
    const props = makeProps({ dark: true });
    const { getByTestId } = render(<LiveShell {...props} />);

    expect(getByTestId("live-shell").className).toContain("bg-zinc-900/90");
  });
});
