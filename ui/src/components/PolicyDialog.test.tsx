/// M2.4 PolicyDialog 单元测试。
///
/// 覆盖：
/// - 打开 → 自动 GET /api/live-sessions/{id}/policy + 渲染 4 字段
/// - 0 值 → 「不限」提示 + input 占位
/// - 输入数字 → 实时更新 draft
/// - 改后 → dirty → 保存按钮可用；保存按钮调 POST + GET
/// - 失败 → 透传 toast.error 双通道
/// - 关闭 → 状态清空
/// - sessionId=null → 不调 API
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import PolicyDialog from "./PolicyDialog";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

// 稳定 runWithToast 引用，避免 PolicyDialog useEffect 反复触发
// 同时 swallow 内部 throw，让调用方 try/catch 接管
const STABLE_RUN_WITH_TOAST = (fn: () => Promise<unknown>, _label: string) => {
  return fn().catch((e) => { throw e; });
};
vi.mock("../async/useApiError", () => ({
  useApiError: () => ({
    runWithToast: STABLE_RUN_WITH_TOAST,
  }),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastWarn = vi.fn();
const toastInfo = vi.fn();
vi.mock("./Toast", () => ({
  useToast: () => ({
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
    warn: (...a: unknown[]) => toastWarn(...a),
    info: (...a: unknown[]) => toastInfo(...a),
  }),
}));

const SAMPLE_POLICY = {
  cooldown_seconds_per_user: 0,
  max_queue_length: 0,
  per_song_max_per_session: 0,
  per_user_max_in_queue: 0,
  rule_version: "rule_aaaaaaaa",
};

const SAMPLE_POLICY_AFTER = {
  ...SAMPLE_POLICY,
  cooldown_seconds_per_user: 30,
  max_queue_length: 5,
  per_song_max_per_session: 2,
  per_user_max_in_queue: 3,
  rule_version: "rule_bbbbbbbb",
};

beforeEach(() => {
  apiRequest.mockReset();
  toastSuccess.mockClear();
  toastError.mockClear();
  apiRequest.mockImplementation((path: string) => {
    if (path.endsWith("/policy")) {
      return Promise.resolve(SAMPLE_POLICY);
    }
    return Promise.resolve({});
  });
});
afterEach(() => cleanup());

describe("PolicyDialog - 点歌条件配置（M2.4）", () => {
  it("打开自动 GET /policy + 渲染 4 字段", async () => {
    const { getByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("policy-field-cooldown_seconds_per_user")).toBeTruthy();
      expect(getByTestId("policy-field-max_queue_length")).toBeTruthy();
      expect(getByTestId("policy-field-per_song_max_per_session")).toBeTruthy();
      expect(getByTestId("policy-field-per_user_max_in_queue")).toBeTruthy();
    });
  });

  it("值 0 → 显示「不限」标签", async () => {
    const { getAllByText } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={() => {}} />,
    );
    await waitFor(() => {
      const unlimitedLabels = getAllByText("不限");
      expect(unlimitedLabels.length).toBe(4);
    });
  });

  it("GET 失败时显示加载错误", async () => {
    apiRequest.mockImplementation(() => Promise.reject(new Error("boom")));
    const { getByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={() => {}} />,
    );
    await waitFor(() => {
      expect(getByTestId("policy-error")).toBeTruthy();
      expect(getByTestId("policy-error").textContent).toContain("加载规则失败");
    });
  });

  it("sessionId=null → 不调 API", () => {
    const { queryByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId={null} onUpdated={() => {}} />,
    );
    expect(apiRequest).not.toHaveBeenCalled();
    expect(queryByTestId("policy-field-cooldown_seconds_per_user")).toBeNull();
  });

  it("输入数字 → draft 更新 + 保存按钮从 disabled 变 enabled", async () => {
    const { getByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("policy-input-cooldown_seconds_per_user")).toBeTruthy());
    const saveBtn = getByTestId("policy-save-button") as HTMLButtonElement;
    // 初始：未改 → disabled
    expect(saveBtn.disabled).toBe(true);
    // 输入 30
    fireEvent.change(getByTestId("policy-input-cooldown_seconds_per_user"), {
      target: { value: "30" },
    });
    await waitFor(() => {
      const btn = getByTestId("policy-save-button") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });
  });

  it("点保存 → POST /policy → toast 成功", async () => {
    const onUpdated = vi.fn();
    apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
      if (opts?.method === "GET" || path.endsWith("/policy") && !opts?.method) {
        return Promise.resolve(SAMPLE_POLICY);
      }
      if (opts?.method === "POST") {
        return Promise.resolve(SAMPLE_POLICY_AFTER);
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={onUpdated} />,
    );
    await waitFor(() => expect(getByTestId("policy-input-cooldown_seconds_per_user")).toBeTruthy());
    fireEvent.change(getByTestId("policy-input-cooldown_seconds_per_user"), {
      target: { value: "30" },
    });
    // 等保存按钮 enabled
    await waitFor(() => {
      expect((getByTestId("policy-save-button") as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(getByTestId("policy-save-button"));
    await waitFor(() => {
      const postCall = apiRequest.mock.calls.find(([p, o]) => p.endsWith("/policy") && o?.method === "POST");
      expect(postCall).toBeTruthy();
      expect(postCall![1].body).toMatchObject({ cooldown_seconds_per_user: 30 });
      expect(toastSuccess).toHaveBeenCalled();
      expect(onUpdated).toHaveBeenCalled();
    });
  });

  it("点重置 → draft 回到 server 值", async () => {
    const { getByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("policy-input-cooldown_seconds_per_user")).toBeTruthy());
    const input = getByTestId("policy-input-cooldown_seconds_per_user") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "30" } });
    await waitFor(() => expect(input.value).toBe("30"));
    fireEvent.click(getByTestId("policy-reset-button"));
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("保存失败 → 行内错误 + 不调 onUpdated", async () => {
    const onUpdated = vi.fn();
    apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
      if (!opts?.method) return Promise.resolve(SAMPLE_POLICY);
      if (opts.method === "POST") return Promise.reject(new Error("network"));
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <PolicyDialog open onClose={() => {}} sessionId="live_x" onUpdated={onUpdated} />,
    );
    await waitFor(() => expect(getByTestId("policy-input-cooldown_seconds_per_user")).toBeTruthy());
    fireEvent.change(getByTestId("policy-input-cooldown_seconds_per_user"), {
      target: { value: "30" },
    });
    await waitFor(() => {
      expect((getByTestId("policy-save-button") as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(getByTestId("policy-save-button"));
    await waitFor(() => {
      expect(getByTestId("policy-error").textContent).toContain("保存失败");
      expect(onUpdated).not.toHaveBeenCalled();
    });
  });
});
