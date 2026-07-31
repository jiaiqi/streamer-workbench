/// ParamInspector 单元测试：覆盖 6 种 kind 的渲染 + 交互。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ParamInspector from "./ParamInspector";
import type { ParamSpec } from "../types";

const intSpec: ParamSpec = {
  key: "margin", label: "边距", kind: "int", default: 58,
  min: 0, max: 200, step: 2, unit: "px", group: "画布", help: "四边留白",
};
const boolSpec: ParamSpec = {
  key: "show_date", label: "显示日期", kind: "bool", default: true, group: "样式",
};
const selectSpec: ParamSpec = {
  key: "columns", label: "栏数", kind: "select", default: 2,
  choices: [2, 3], group: "布局",
};
const sectionMapSpec: ParamSpec = {
  key: "columns_per_section", label: "每分组栏数", kind: "section_map",
  default: { "一字": 1, "二字": 3, "三字": 2 },
  section_axis: "chars", group: "布局", min: 0, max: 10,
};
const floatSpec: ParamSpec = {
  key: "ratio", label: "宽高比", kind: "float", default: 1.5,
  min: 0, max: 10, step: 0.1, group: "画布",
};
const groupOrderSpec: ParamSpec = {
  key: "order", label: "分组顺序", kind: "group_order",
  default: ["一字", "二字", "三字"], group: "布局",
};

afterEach(() => cleanup());

describe("ParamInspector", () => {
  it("按 spec.group 分组", () => {
    const onChange = vi.fn();
    render(
      <ParamInspector
        specs={[intSpec, boolSpec, selectSpec]}
        values={{ margin: 58, show_date: true, columns: 2 }}
        onChange={onChange}
      />,
    );
    expect(screen.getByText("画布")).toBeTruthy();
    expect(screen.getByText("样式")).toBeTruthy();
    expect(screen.getByText("布局")).toBeTruthy();
  });

  it("int: 滑块+数字双向联动", () => {
    const onChange = vi.fn();
    render(
      <ParamInspector specs={[intSpec]} values={{ margin: 58 }} onChange={onChange} />,
    );
    const number = screen.getByTestId("param-number-margin") as HTMLInputElement;
    expect(number.value).toBe("58");
    fireEvent.change(number, { target: { value: "100" } });
    expect(onChange).toHaveBeenCalledWith("margin", 100);
  });

  it("int: unit 显示", () => {
    render(
      <ParamInspector specs={[intSpec]} values={{ margin: 58 }} onChange={vi.fn()} />,
    );
    expect(screen.getByText("(px)")).toBeTruthy();
  });

  it("int: help tooltip 渲染", () => {
    render(
      <ParamInspector specs={[intSpec]} values={{ margin: 58 }} onChange={vi.fn()} />,
    );
    expect(screen.getByText("四边留白")).toBeTruthy();
  });

  it("int: 改值后出现「重置」按钮", () => {
    render(
      <ParamInspector
        specs={[intSpec]} values={{ margin: 100 }} onChange={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    const reset = screen.getByTestId("param-reset-margin");
    expect(reset).toBeTruthy();
  });

  it("int: 默认值时无「重置」按钮", () => {
    render(
      <ParamInspector
        specs={[intSpec]} values={{ margin: 58 }} onChange={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("param-reset-margin")).toBeNull();
  });

  it("int: 点击「重置」调用 onReset", async () => {
    const onReset = vi.fn();
    const user = userEvent.setup();
    render(
      <ParamInspector
        specs={[intSpec]} values={{ margin: 100 }} onChange={vi.fn()}
        onReset={onReset}
      />,
    );
    await user.click(screen.getByTestId("param-reset-margin"));
    expect(onReset).toHaveBeenCalledWith("margin");
  });

  it("bool: 开关切换", () => {
    const onChange = vi.fn();
    render(
      <ParamInspector specs={[boolSpec]} values={{ show_date: false }} onChange={onChange} />,
    );
    const toggle = screen.getByRole("switch");
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith("show_date", true);
  });

  it("select: 数字选项保留类型", () => {
    const onChange = vi.fn();
    render(
      <ParamInspector specs={[selectSpec]} values={{ columns: 2 }} onChange={onChange} />,
    );
    const sel = screen.getByTestId("param-select-columns") as HTMLSelectElement;
    expect(sel.value).toBe("2");
    fireEvent.change(sel, { target: { value: "3" } });
    // selectControl 反序列化时从 spec.choices 找回原始类型
    expect(onChange).toHaveBeenCalledWith("columns", 3);
  });

  it("section_map: 显示所有分组 + 改值时整体回传", () => {
    const onChange = vi.fn();
    render(
      <ParamInspector
        specs={[sectionMapSpec]}
        values={{ columns_per_section: { "一字": 1, "二字": 3, "三字": 2 } }}
        onChange={onChange}
      />,
    );
    expect(screen.getByTestId("param-section-map")).toBeTruthy();
    const yiInput = screen.getByTestId("param-section-map-一字") as HTMLInputElement;
    expect(yiInput.value).toBe("1");
    fireEvent.change(yiInput, { target: { value: "4" } });
    expect(onChange).toHaveBeenCalledWith("columns_per_section", {
      "一字": 4, "二字": 3, "三字": 2,
    });
  });

  it("section_map: value 缺失时回退到 spec.default", () => {
    render(
      <ParamInspector specs={[sectionMapSpec]} values={{}} onChange={vi.fn()} />,
    );
    const yiInput = screen.getByTestId("param-section-map-一字") as HTMLInputElement;
    expect(yiInput.value).toBe("1");
  });

  it("float: 步长 0.1", () => {
    const onChange = vi.fn();
    render(
      <ParamInspector specs={[floatSpec]} values={{ ratio: 1.5 }} onChange={onChange} />,
    );
    const number = screen.getByTestId("param-number-ratio") as HTMLInputElement;
    expect(number.step).toBe("0.1");
  });

  it("group_order: 按顺序展示", () => {
    render(
      <ParamInspector specs={[groupOrderSpec]} values={{ order: ["一字", "二字", "三字"] }} onChange={vi.fn()} />,
    );
    const list = screen.getByRole("list");
    expect(list.children).toHaveLength(3);
    expect(list.textContent).toContain("一字");
    expect(list.textContent).toContain("三字");
  });

  it("空 specs 时显示加载中", () => {
    render(<ParamInspector specs={[]} values={{}} onChange={vi.fn()} />);
    expect(screen.getByText(/参数加载中/)).toBeTruthy();
  });
});
