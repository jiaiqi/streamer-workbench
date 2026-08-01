/// R4.1.3 StatusBadge 单元测试。
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusBadge from "./StatusBadge";

describe("StatusBadge 默认文案", () => {
  it("saved → '已保存'", () => {
    render(<StatusBadge kind="saved" />);
    expect(screen.getByText("已保存")).toBeTruthy();
  });

  it("dirty → '编辑中'", () => {
    render(<StatusBadge kind="dirty" />);
    expect(screen.getByText("编辑中")).toBeTruthy();
  });

  it("saving → '保存中'", () => {
    render(<StatusBadge kind="saving" />);
    expect(screen.getByText("保存中")).toBeTruthy();
  });

  it("error → '失败'", () => {
    render(<StatusBadge kind="error" />);
    expect(screen.getByText("失败")).toBeTruthy();
  });

  it("active → '进行中'", () => {
    render(<StatusBadge kind="active" />);
    expect(screen.getByText("进行中")).toBeTruthy();
  });

  it("closed → '已结束'", () => {
    render(<StatusBadge kind="closed" />);
    expect(screen.getByText("已结束")).toBeTruthy();
  });

  it("draft → '未会'", () => {
    render(<StatusBadge kind="draft" />);
    expect(screen.getByText("未会")).toBeTruthy();
  });
});

describe("StatusBadge 自定义", () => {
  it("label 覆盖默认", () => {
    render(<StatusBadge kind="saved" label="已保存 (5s 前)" />);
    expect(screen.getByText("已保存 (5s 前)")).toBeTruthy();
  });
});

describe("StatusBadge 视觉", () => {
  it("error 暗色用 bg-red-500/15", () => {
    const { container } = render(<StatusBadge kind="error" dark={true} />);
    const span = container.querySelector("span")!;
    expect(span.className).toMatch(/bg-red-500/);
  });

  it("error 亮色用 bg-red-50", () => {
    const { container } = render(<StatusBadge kind="error" dark={false} />);
    const span = container.querySelector("span")!;
    expect(span.className).toMatch(/bg-red-50/);
  });

  it("active 暗色用 bg-emerald-500/15", () => {
    const { container } = render(<StatusBadge kind="active" dark={true} />);
    const span = container.querySelector("span")!;
    expect(span.className).toMatch(/bg-emerald-500/);
  });

  it("data-status 透传 kind", () => {
    render(<StatusBadge kind="saving" data-testid="badge" />);
    expect(screen.getByTestId("badge").getAttribute("data-status")).toBe("saving");
  });

  it("compact 模式 padding 缩小", () => {
    const { container } = render(<StatusBadge kind="saved" compact />);
    const span = container.querySelector("span")!;
    expect(span.className).toMatch(/px-1\.5/);
  });
});
