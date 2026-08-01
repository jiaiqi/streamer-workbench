/// R4.1.2 Spinner 单元测试。
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import Spinner from "./Spinner";

describe("Spinner 形态", () => {
  it("默认 md (18px)", () => {
    const { container } = render(<Spinner />);
    const span = container.querySelector("span")!;
    expect(span.style.width).toBe("18px");
    expect(span.style.height).toBe("18px");
  });

  it("size=sm (12px)", () => {
    const { container } = render(<Spinner size="sm" />);
    const span = container.querySelector("span")!;
    expect(span.style.width).toBe("12px");
  });

  it("size=lg (24px)", () => {
    const { container } = render(<Spinner size="lg" />);
    const span = container.querySelector("span")!;
    expect(span.style.width).toBe("24px");
  });

  it("tone=primary 设置 borderTopColor 为 var(--color-primary)", () => {
    const { container } = render(<Spinner tone="primary" />);
    const span = container.querySelector("span")!;
    expect(span.style.borderTopColor).toBe("var(--color-primary)");
  });

  it("tone=current 不设置 borderTopColor", () => {
    const { container } = render(<Spinner />);
    const span = container.querySelector("span")!;
    expect(span.style.borderTopColor).toBe("");
  });
});

describe("Spinner 无障碍", () => {
  it("默认 role=status + aria-label", () => {
    render(<Spinner />);
    const span = screen.getByRole("status");
    expect(span.getAttribute("aria-label")).toBe("加载中");
  });

  it("label 自定义", () => {
    render(<Spinner label="渲染中" />);
    expect(screen.getByLabelText("渲染中")).toBeTruthy();
  });

  it("decorative=true → aria-hidden, 无 role", () => {
    const { container } = render(<Spinner decorative={true} />);
    const span = container.querySelector("span")!;
    expect(span.getAttribute("aria-hidden")).toBe("true");
    expect(span.getAttribute("role")).toBeNull();
  });
});

describe("Spinner 集成", () => {
  it("className 透传 + 与 animate-spin 同时存在", () => {
    const { container } = render(<Spinner className="custom-cls" />);
    const span = container.querySelector("span")!;
    expect(span.className).toMatch(/animate-spin/);
    expect(span.className).toMatch(/custom-cls/);
  });
});
