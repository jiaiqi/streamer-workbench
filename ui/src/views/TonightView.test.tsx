/// P1-A1.1 TonightView 测试（3 个 spec）。
///
/// 覆盖（容器层职责，不重复 TonightWorkbench 5 区的测试）：
/// 1. 渲染：屏幕标题 + 「进入海报工作台」CTA + 透传 4+3 回调后 TonightWorkbench 5 区挂载
/// 2. 透传 onPlaySong / onCreatePosterFromTop / onSwitchToStats / onOpenLiveView 全部 4 个必传回调
/// 3. CTA「进入海报工作台」→ onGoToWorkspace 被调一次
///
/// 设计：mock 整个 TonightWorkbench（避免引入 5 区内部 apiRequest 链），只断言容器层行为。
///     WorkspacePosterBridge 也 mock 掉（它有自己的 store 状态机，独立单测覆盖）。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock TonightWorkbench：简单 <div data-testid="tonight-workbench-stub" /> 替代
// 避免引入 5 区 effect 链。
vi.mock("../components/TonightWorkbench", () => ({
  default: function TonightWorkbenchStub(props: Record<string, unknown>) {
    // 暴露回调名到 data-attrs，让测试可以断言"哪些回调被传了"
    const cbNames = Object.keys(props).filter(k => k.startsWith("on"));
    return (
      <div data-testid="tonight-workbench-stub" data-cb-count={cbNames.length}>
        {cbNames.map(name => (
          <span key={name} data-testid={`stub-cb-${name}`}>{name}</span>
        ))}
      </div>
    );
  },
}));

vi.mock("../posters/WorkspacePosterBridge", () => ({
  default: function BridgeStub() {
    return <div data-testid="tonight-poster-bridge-stub" />;
  },
}));

afterEach(() => cleanup());

import TonightView from "./TonightView";

const baseProps = {
  dark: false,
  themes: [{ name: "海洋柔光" }, { name: "月夜星河" }],
  onSelectTheme: vi.fn(),
  onSelectCanvas: vi.fn(),
  onGoToWorkspace: vi.fn(),
  onPlaySong: vi.fn(),
  onOpenLiveView: vi.fn(),
  onCreatePosterFromTop: vi.fn(async () => {}),
  onSwitchToStats: vi.fn(),
  onGenerateRecap: vi.fn(),
  onGenerateLearningReport: vi.fn(),
  onOpenQuickView: vi.fn(),
};

describe("TonightView 容器层", () => {
  it("渲染屏幕标题 + 5 区 TonightWorkbench + 进入工作台 CTA", () => {
    render(<TonightView {...baseProps} />);
    // 屏幕标题
    expect(screen.getByTestId("tonight-view-header")).toBeTruthy();
    expect(screen.getByText("开播前 · 准备")).toBeTruthy();
    expect(screen.getByText(/先看就绪度，再开直播/)).toBeTruthy();
    // TonightWorkbench 5 区（被 mock 成 stub，但 data-testid 仍在）
    expect(screen.getByTestId("tonight-workbench-stub")).toBeTruthy();
    // CTA
    expect(screen.getByTestId("tonight-go-to-workspace")).toBeTruthy();
    expect(screen.getByText("进入海报工作台")).toBeTruthy();
  });

  it("透传 4+3 必选/可选回调到 TonightWorkbench", () => {
    render(<TonightView {...baseProps} />);
    // 7 个回调：onPlaySong / onOpenLiveView / onCreatePosterFromTop / onSwitchToStats
    //       + onGenerateRecap / onGenerateLearningReport / onOpenQuickView
    const stub = screen.getByTestId("tonight-workbench-stub");
    expect(stub.getAttribute("data-cb-count")).toBe("7");
    // 列举所有回调名（按 TonightWorkbench props 顺序）
    for (const name of [
      "onPlaySong",
      "onOpenLiveView",
      "onCreatePosterFromTop",
      "onSwitchToStats",
      "onGenerateRecap",
      "onGenerateLearningReport",
      "onOpenQuickView",
    ]) {
      expect(screen.getByTestId(`stub-cb-${name}`)).toBeTruthy();
    }
  });

  it("点 CTA「进入海报工作台」→ onGoToWorkspace 被调一次", async () => {
    const onGoToWorkspace = vi.fn();
    render(<TonightView {...baseProps} onGoToWorkspace={onGoToWorkspace} />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("tonight-go-to-workspace"));
    expect(onGoToWorkspace).toHaveBeenCalledTimes(1);
  });
});
