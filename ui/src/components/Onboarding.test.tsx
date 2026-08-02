/// L1.3 Onboarding 测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import Onboarding, { isOnboarded, markOnboarded, resetOnboarded } from "./Onboarding";

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("Onboarding - 显示逻辑", () => {
  it("localStorage 未标记 + 没 forceShow → 显示引导", async () => {
    render(<Onboarding />);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-panel"]')).toBeTruthy();
    });
  });

  it("localStorage 已标记 → 不显示", async () => {
    markOnboarded();
    render(<Onboarding />);
    // 等待一帧 useEffect 跑完
    await new Promise(r => setTimeout(r, 50));
    expect(document.querySelector('[data-testid="onboarding-panel"]')).toBeNull();
  });

  it("forceShow=true 即使已 onboarded 也显示", async () => {
    markOnboarded();
    render(<Onboarding forceShow={true} />);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-panel"]')).toBeTruthy();
    });
  });
});

describe("Onboarding - 步骤导航", () => {
  it("初始显示第 1 步", async () => {
    render(<Onboarding />);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-title"]')?.textContent).toBe("欢迎来到主播工作台");
    });
    expect(document.querySelector('[data-testid="onboarding-dot-0"]')?.getAttribute("data-active")).toBe("true");
    expect(document.querySelector('[data-testid="onboarding-dot-1"]')?.getAttribute("data-active")).toBe("false");
  });

  it("点「下一步」→ 切到第 2 步", async () => {
    render(<Onboarding />);
    await waitFor(() => expect(document.querySelector('[data-testid="onboarding-next"]')).toBeTruthy());
    fireEvent.click(document.querySelector('[data-testid="onboarding-next"]')!);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-title"]')?.textContent).toBe("排版 + 主题");
    });
    expect(document.querySelector('[data-testid="onboarding-dot-1"]')?.getAttribute("data-active")).toBe("true");
  });

  it("点「上一步」→ 回到上一步（首步禁用）", async () => {
    render(<Onboarding />);
    await waitFor(() => expect(document.querySelector('[data-testid="onboarding-back"]')).toBeTruthy());
    const backBtn = document.querySelector('[data-testid="onboarding-back"]') as HTMLButtonElement;
    expect(backBtn.disabled).toBe(true);

    // 先走到第 2 步
    fireEvent.click(document.querySelector('[data-testid="onboarding-next"]')!);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-title"]')?.textContent).toBe("排版 + 主题");
    });
    // 上一步可用
    const backBtn2 = document.querySelector('[data-testid="onboarding-back"]') as HTMLButtonElement;
    expect(backBtn2.disabled).toBe(false);
    fireEvent.click(backBtn2);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-title"]')?.textContent).toBe("欢迎来到主播工作台");
    });
  });

  it("最后一步点「开始使用」→ 关闭 + 写 localStorage + 调 onClose", async () => {
    const onClose = vi.fn();
    render(<Onboarding onClose={onClose} />);
    await waitFor(() => expect(document.querySelector('[data-testid="onboarding-next"]')).toBeTruthy());
    fireEvent.click(document.querySelector('[data-testid="onboarding-next"]')!);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-title"]')?.textContent).toBe("排版 + 主题");
    });
    fireEvent.click(document.querySelector('[data-testid="onboarding-next"]')!);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-title"]')?.textContent).toBe("弹唱 + 找歌 + 快捷键");
    });
    fireEvent.click(document.querySelector('[data-testid="onboarding-next"]')!);
    // 关闭 + localStorage
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-panel"]')).toBeNull();
    });
    expect(isOnboarded()).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("点「跳过」→ 立即关闭 + 写 localStorage", async () => {
    render(<Onboarding />);
    await waitFor(() => expect(document.querySelector('[data-testid="onboarding-skip"]')).toBeTruthy());
    fireEvent.click(document.querySelector('[data-testid="onboarding-skip"]')!);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="onboarding-panel"]')).toBeNull();
    });
    expect(isOnboarded()).toBe(true);
  });
});

describe("Onboarding - 辅助函数", () => {
  it("isOnboarded() 初始 false", () => {
    expect(isOnboarded()).toBe(false);
  });

  it("markOnboarded() 后 isOnboarded() 返回 true", () => {
    markOnboarded();
    expect(isOnboarded()).toBe(true);
  });

  it("resetOnboarded() 后 isOnboarded() 返回 false", () => {
    markOnboarded();
    resetOnboarded();
    expect(isOnboarded()).toBe(false);
  });

  it("STORAGE_VERSION 升级后旧标记视为未 onboarded", async () => {
    markOnboarded();
    // 模拟版本升级：直接覆盖 localStorage
    localStorage.setItem("sw-onboarded", "v0");
    expect(isOnboarded()).toBe(false);
  });
});
