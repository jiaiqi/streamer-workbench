/// M3 P3 续: useIntersection hook + ThemeLazyThumb 测试。
///
/// 测试策略：直接用 JSX `ref={ref}` 挂到 DOM 元素上 — 这是 useIntersection 的真实使用方式
/// （ThemeLazyThumb 内部就是这样用），useEffect 在 commit 之后跑，ref.current 已被设置，
/// observer 能正常创建。
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { useIntersection } from "./useIntersection";
import { ThemeLazyThumb } from "@/components/ThemeLazyThumb";

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];
  callback: IntersectionObserverCallback;
  options: IntersectionObserverInit | undefined;
  elements: Element[] = [];
  disconnected = false;

  constructor(cb: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    this.callback = cb;
    this.options = options;
    MockIntersectionObserver.instances.push(this);
  }
  observe(el: Element) { this.elements.push(el); }
  unobserve() {}
  disconnect() { this.disconnected = true; }
  trigger(isIntersecting: boolean) {
    this.callback(
      this.elements.map((el) => ({
        isIntersecting,
        target: el,
        boundingClientRect: el.getBoundingClientRect(),
        intersectionRatio: isIntersecting ? 1 : 0,
        intersectionRect: el.getBoundingClientRect(),
        rootBounds: null,
        time: Date.now(),
      })) as IntersectionObserverEntry[],
      this as unknown as IntersectionObserver,
    );
  }
}

function Probe(props: { once?: boolean; rootMargin?: string }) {
  const [ref, visible] = useIntersection<HTMLDivElement>(props);
  return (
    <div>
      <div ref={ref} data-testid="target" />
      <span data-testid="state">{visible ? "visible" : "hidden"}</span>
    </div>
  );
}

describe("useIntersection hook", () => {
  beforeEach(() => {
    global.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
    MockIntersectionObserver.instances = [];
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("初始时 isIntersecting=false", () => {
    render(<Probe />);
    expect(screen.getByTestId("state").textContent).toBe("hidden");
  });

  it("进入视口触发可见", async () => {
    render(<Probe />);
    const obs = MockIntersectionObserver.instances[0];
    expect(obs).toBeDefined();
    obs.trigger(true);
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("visible");
    });
  });

  it("once=true：进入一次后 disconnect", async () => {
    render(<Probe once={true} />);
    const obs = MockIntersectionObserver.instances[0];
    obs.trigger(true);
    await waitFor(() => {
      expect(obs.disconnected).toBe(true);
    });
  });

  it("once=false：离开视口再次隐藏", async () => {
    render(<Probe once={false} />);
    const obs = MockIntersectionObserver.instances[0];
    obs.trigger(true);
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("visible");
    });
    obs.trigger(false);
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("hidden");
    });
  });

  it("无 IntersectionObserver（SSR/旧浏览器）兜底为可见", () => {
    const orig = global.IntersectionObserver;
    // @ts-expect-error - 故意删除模拟旧环境
    delete global.IntersectionObserver;
    render(<Probe />);
    expect(screen.getByTestId("state").textContent).toBe("visible");
    global.IntersectionObserver = orig;
  });
});


describe("ThemeLazyThumb 组件", () => {
  beforeEach(() => {
    global.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
    MockIntersectionObserver.instances = [];
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("未进入视口时 src 为空（不发请求）", () => {
    render(<ThemeLazyThumb name="海洋柔光" />);
    const img = screen.getByTestId("theme-lazy-thumb");
    expect(img.getAttribute("src")).toBeNull();
  });

  it("进入视口后 src 设置", async () => {
    render(<ThemeLazyThumb name="海洋柔光" />);
    const obs = MockIntersectionObserver.instances[0];
    expect(obs).toBeDefined();
    obs.trigger(true);
    await waitFor(() => {
      const img = screen.getByTestId("theme-lazy-thumb");
      expect(img.getAttribute("src")).toBe("/api/thumb/%E6%B5%B7%E6%B4%8B%E6%9F%94%E5%85%89");
    });
  });

  it("data-theme-name 属性正确", () => {
    render(<ThemeLazyThumb name="月夜星河" />);
    const img = screen.getByTestId("theme-lazy-thumb");
    expect(img.getAttribute("data-theme-name")).toBe("月夜星河");
  });

  it("onError 隐藏元素", () => {
    render(<ThemeLazyThumb name="x" />);
    const img = screen.getByTestId("theme-lazy-thumb") as HTMLImageElement;
    img.dispatchEvent(new Event("error"));
    expect(img.style.display).toBe("none");
  });
});
