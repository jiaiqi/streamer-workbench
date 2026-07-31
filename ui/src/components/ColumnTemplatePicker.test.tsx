/// ColumnTemplatePicker 单元测试：模板下拉 + 选中应用 + value 反推当前模板。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ColumnTemplatePicker from "./ColumnTemplatePicker";
import type { ColumnTemplate } from "../types";

const templates: ColumnTemplate[] = [
  { key: "balanced", label: "均衡", description: "每组 2 栏",
    values: { "一字": 2, "二字": 2, "三字": 2, "四字": 2, "五字": 2, "六字": 2, "长歌名": 2, "其他": 2 } },
  { key: "dense", label: "密集", description: "1-2 字 3 栏, 3-4 字 2 栏",
    values: { "一字": 3, "二字": 3, "三字": 2, "四字": 2, "五字": 1, "六字": 1, "长歌名": 1, "其他": 1 } },
  { key: "custom", label: "自定义", description: "手动编辑", values: {} },
];

afterEach(() => cleanup());

describe("ColumnTemplatePicker", () => {
  it("渲染下拉 + 描述", () => {
    render(<ColumnTemplatePicker templates={templates} value={{}} onChange={vi.fn()} />);
    expect(screen.getByTestId("column-template-picker")).toBeTruthy();
    expect(screen.getByTestId("column-template-select")).toBeTruthy();
  });

  it("空 value 默认为 custom", () => {
    render(<ColumnTemplatePicker templates={templates} value={{}} onChange={vi.fn()} />);
    const sel = screen.getByTestId("column-template-select") as HTMLSelectElement;
    expect(sel.value).toBe("custom");
  });

  it("value 匹配 balanced → 选中 balanced", () => {
    render(
      <ColumnTemplatePicker
        templates={templates}
        value={{ "一字": 2, "二字": 2, "三字": 2, "四字": 2, "五字": 2, "六字": 2, "长歌名": 2, "其他": 2 }}
        onChange={vi.fn()}
      />,
    );
    const sel = screen.getByTestId("column-template-select") as HTMLSelectElement;
    expect(sel.value).toBe("balanced");
  });

  it("value 匹配 dense → 选中 dense", () => {
    render(
      <ColumnTemplatePicker
        templates={templates}
        value={{ "一字": 3, "二字": 3, "三字": 2, "四字": 2, "五字": 1, "六字": 1, "长歌名": 1, "其他": 1 }}
        onChange={vi.fn()}
      />,
    );
    const sel = screen.getByTestId("column-template-select") as HTMLSelectElement;
    expect(sel.value).toBe("dense");
  });

  it("value 与任何模板都不匹配 → custom", () => {
    render(
      <ColumnTemplatePicker
        templates={templates}
        value={{ "一字": 5, "二字": 5, "三字": 5, "四字": 5, "五字": 5, "六字": 5, "长歌名": 5, "其他": 5 }}
        onChange={vi.fn()}
      />,
    );
    const sel = screen.getByTestId("column-template-select") as HTMLSelectElement;
    expect(sel.value).toBe("custom");
  });

  it("选非自定义模板 → onChange 收到模板 values", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ColumnTemplatePicker templates={templates} value={{}} onChange={onChange} />,
    );
    const sel = screen.getByTestId("column-template-select") as HTMLSelectElement;
    await user.selectOptions(sel, "dense");
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual({
      "一字": 3, "二字": 3, "三字": 2, "四字": 2,
      "五字": 1, "六字": 1, "长歌名": 1, "其他": 1,
    });
  });

  it("选 custom → onChange 不被调用（保持当前 value）", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ColumnTemplatePicker templates={templates} value={{}} onChange={onChange} />,
    );
    const sel = screen.getByTestId("column-template-select") as HTMLSelectElement;
    await user.selectOptions(sel, "custom");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("显示当前模板的描述（按 value 反推后）", () => {
    render(
      <ColumnTemplatePicker
        templates={templates}
        value={{ "一字": 3, "二字": 3, "三字": 2, "四字": 2, "五字": 1, "六字": 1, "长歌名": 1, "其他": 1 }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/1-2 字 3 栏/)).toBeTruthy();
  });
});
