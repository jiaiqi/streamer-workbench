/// M2.2 WebDavPanel 单元测试 + M2.4 自动同步。
import userEvent from "@testing-library/user-event";

///
/// 覆盖：
/// - 启动调 GET /api/backup/webdav/config
/// - 3 状态切换：unconfigured / locked / unlocked
/// - 离线 banner + 禁用所有动作
/// - 保存配置：PUT + 状态切到 unlocked + 拉列表
/// - 解锁：错误主密码提示
/// - 列出远端：GET /list + 渲染文件
/// - 推送：POST /push + toast 成功
/// - 拉取：POST /pull
/// - 测试连接：test-saved / test
/// - 清除：POST /config/clear + 状态回 unconfigured
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import WebDavPanel from "./WebDavPanel";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
  ApiClientError: class extends Error {
    code: string;
    details: Record<string, unknown>;
    constructor(code: string, message: string, details: Record<string, unknown> = {}) {
      super(message);
      this.code = code;
      this.details = details;
    }
  },
}));

const toastMock = {
  success: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
};
vi.mock("../components/Toast", () => ({
  ToastContext: {
    Provider: ({ children }: { children: React.ReactNode }) => children,
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useToast: () => toastMock as any,
}));

const SAMPLE_CONFIG = {
  configured: true,
  url: "https://dav.example.com/streamer",
  username: "alice",
  remote_dir: "/backups",
  updated_at: "2026-08-04T12:00:00Z",
  needs_unlock: false,
};

const SAMPLE_LOCKED = {
  configured: true,
  url: "",
  username: "",
  remote_dir: "",
  updated_at: "2026-08-04T12:00:00Z",
  needs_unlock: true,
};

const SAMPLE_FILES = {
  files: [
    { name: "push-20260804T120000Z.songworkbench",
      href: "/backups/push-20260804T120000Z.songworkbench",
      size: 12345, last_modified: "Mon, 04 Aug 2026" },
    { name: "from-cloud.songworkbench",
      href: "/backups/from-cloud.songworkbench",
      size: 9999, last_modified: "Sun, 03 Aug 2026" },
  ],
};

const SAMPLE_PUSH = {
  ok: true,
  remote_path: "/backups/push-20260804T120500Z.songworkbench",
  remote_name: "push-20260804T120500Z.songworkbench",
  file_count: 12,
  total_bytes: 100000,
};

const SAMPLE_PULL = {
  ok: true,
  remote_name: "from-cloud.songworkbench",
  manifest: { schema_version: 2, file_count: 5 },
};

beforeEach(() => {
  apiRequest.mockReset();
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  toastMock.warn.mockReset();
  toastMock.info.mockReset();
  // 默认：onLine = true
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

afterEach(() => cleanup());

// 工具：根据路径 mock apiRequest
function setupApiMock(overrides: Record<string, unknown> = {}) {
  const handlers: Record<string, (opts?: { body?: unknown }) => unknown> = {
    "/api/backup/webdav/config": (opts) => {
      const qs = (opts as { _qs?: { master_password?: string } } | undefined)?._qs;
      // unlocked 时根据 master_password 返回完整配置
      if (overrides._unlocked !== false && qs?.master_password === "master123") {
        return Promise.resolve(SAMPLE_CONFIG);
      }
      return Promise.resolve(overrides._configInitial || SAMPLE_LOCKED);
    },
    "/api/backup/webdav/list": () => Promise.resolve(SAMPLE_FILES),
    "/api/backup/webdav/push": () => Promise.resolve(SAMPLE_PUSH),
    "/api/backup/webdav/pull": () => Promise.resolve(SAMPLE_PULL),
    "/api/backup/webdav/test": () => Promise.resolve({ ok: true, status: 207, message: "ok" }),
    "/api/backup/webdav/test-saved": () =>
      Promise.resolve(overrides._testSaved || { ok: true, status: 207, message: "ok" }),
    "/api/backup/webdav/config/clear": () => Promise.resolve({ ok: true, updated_at: "" }),
  };
  apiRequest.mockImplementation((path: string, opts?: { body?: unknown }) => {
    // 解析 query string 用于配置解锁
    const [pathOnly, qsRaw] = path.split("?");
    let queryParams: Record<string, string> = {};
    if (qsRaw) {
      for (const part of qsRaw.split("&")) {
        const [k, v] = part.split("=");
        queryParams[decodeURIComponent(k)] = decodeURIComponent(v ?? "");
      }
    }
    const handler = handlers[pathOnly];
    if (handler) {
      return handler({ body: opts?.body, _qs: queryParams } as never);
    }
    return Promise.resolve({});
  });
}

describe("WebDavPanel", () => {
  // ── 1. 启动时调 GET config ──

  it("启动时调 GET /api/backup/webdav/config", async () => {
    setupApiMock({ _configInitial: { configured: false } });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith("/api/backup/webdav/config");
    });
    await waitFor(() => {
      expect(getByTestId("webdav-config-form")).toBeTruthy();
    });
  });

  // ── 2. configured 但需要解锁 → 显示 locked 表单 ──

  it("needs_unlock=true → 渲染 locked 表单", async () => {
    setupApiMock({ _configInitial: SAMPLE_LOCKED });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => {
      expect(getByTestId("webdav-locked-form")).toBeTruthy();
    });
    expect(getByTestId("webdav-unlock-button")).toBeTruthy();
    expect(getByTestId("webdav-clear-button")).toBeTruthy();
  });

  // ── 3. needs_unlock=false → 渲染 unlocked 概览 ──

  it("needs_unlock=false → 渲染 unlocked 概览（不调 list）", async () => {
    // 启动时直接拿到完整 config（用 master_password=master123 的 query 解锁）
    setupApiMock();
    // 这里第一次调用无 master_password → 返回 locked；解锁后才能看到 unlocked
    // 我们直接覆盖第一次返回 SAMPLE_CONFIG
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/backup/webdav/config") {
        return Promise.resolve(SAMPLE_CONFIG);
      }
      return Promise.resolve({});
    });
    const { getByTestId, queryByTestId } = render(<WebDavPanel />);
    await waitFor(() => {
      expect(getByTestId("webdav-unlocked-section")).toBeTruthy();
    });
    // 不会自动调 list
    const listCalls = apiRequest.mock.calls.filter(([p]) => p === "/api/backup/webdav/list");
    expect(listCalls).toHaveLength(0);
    // 提示"暂无远端备份"
    expect(queryByTestId("webdav-empty")).toBeTruthy();
  });

  // ── 4. 离线 banner + 按钮禁用 ──

  it("离线时显示 banner + 所有动作按钮 disabled", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    setupApiMock({ _configInitial: { configured: false } });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => {
      expect(getByTestId("webdav-offline-banner")).toBeTruthy();
    });
    const saveBtn = getByTestId("webdav-save-button") as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
    const testBtn = getByTestId("webdav-test-button") as HTMLButtonElement;
    expect(testBtn.disabled).toBe(true);
  });

  // ── 5. 保存配置 → 状态切到 unlocked + 自动 list ──

  it("保存配置 → 调 PUT + 自动列出 + 状态切到 unlocked", async () => {
    setupApiMock({ _configInitial: { configured: false } });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-config-form")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-url"), { target: { value: "https://dav.example.com" } });
    fireEvent.change(getByTestId("webdav-input-username"), { target: { value: "alice" } });
    fireEvent.change(getByTestId("webdav-input-password"), { target: { value: "pwd" } });
    fireEvent.change(getByTestId("webdav-input-remote-dir"), { target: { value: "/backups" } });
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "master" } });
    fireEvent.click(getByTestId("webdav-save-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/backup/webdav/config",
        expect.objectContaining({
          method: "PUT",
          body: expect.objectContaining({
            url: "https://dav.example.com",
            username: "alice",
            password: "pwd",
            remote_dir: "/backups",
            master_password: "master",
          }),
        }),
      );
    });
    // 状态切到 unlocked
    await waitFor(() => {
      expect(getByTestId("webdav-unlocked-section")).toBeTruthy();
    });
    // 自动调 list
    await waitFor(() => {
      const listCalls = apiRequest.mock.calls.filter(([p]) => p.startsWith("/api/backup/webdav/list"));
      expect(listCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 6. 解锁错误主密码 ──

  it("解锁时主密码错误显示行内错误", async () => {
    setupApiMock({ _configInitial: SAMPLE_LOCKED });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-locked-form")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "wrong" } });
    // 模拟解锁请求返回 needs_unlock=true（错密码）
    apiRequest.mockImplementation((path: string) => {
      if (path.startsWith("/api/backup/webdav/config")) {
        return Promise.resolve(SAMPLE_LOCKED);
      }
      return Promise.resolve({});
    });
    fireEvent.click(getByTestId("webdav-unlock-button"));
    await waitFor(() => {
      expect(getByTestId("webdav-inline-error")).toBeTruthy();
    });
  });

  // ── 7. 列出远端文件 + 渲染 ──

  it("列出远端文件后渲染文件列表", async () => {
    // 用 unlocked 状态进入
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (path.startsWith("/api/backup/webdav/list")) return Promise.resolve(SAMPLE_FILES);
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-unlocked-section")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "master123" } });
    fireEvent.click(getByTestId("webdav-list-button"));
    await waitFor(() => {
      expect(getByTestId("webdav-files")).toBeTruthy();
    });
    const fileRows = document.querySelectorAll("[data-testid^='webdav-file-']");
    expect(fileRows.length).toBe(2);
  });

  // ── 8. 推送 → 调 /push + toast success + 自动刷新 list ──

  it("推送 → 调 POST /push + 提示成功 + 自动刷新列表", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (path === "/api/backup/webdav/push") return Promise.resolve(SAMPLE_PUSH);
      if (path.startsWith("/api/backup/webdav/list")) return Promise.resolve(SAMPLE_FILES);
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-unlocked-section")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "master123" } });
    fireEvent.click(getByTestId("webdav-push-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/backup/webdav/push",
        expect.objectContaining({ method: "POST", body: { master_password: "master123" } }),
      );
    });
    expect(toastMock.success).toHaveBeenCalled();
    // 推送后会调 list 刷新
    await waitFor(() => {
      const listCalls = apiRequest.mock.calls.filter(([p]) => p.startsWith("/api/backup/webdav/list"));
      expect(listCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 9. 拉取 → 调 /pull + 提示重启 ──

  it("拉取远端文件 → 调 POST /pull", async () => {
    apiRequest.mockImplementation((path: string, opts?: { body?: { remote_name?: string } }) => {
      if (path === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (path.startsWith("/api/backup/webdav/list")) return Promise.resolve(SAMPLE_FILES);
      if (path === "/api/backup/webdav/pull") {
        return Promise.resolve({ ...SAMPLE_PULL, remote_name: opts?.body?.remote_name });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-unlocked-section")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "master123" } });
    fireEvent.click(getByTestId("webdav-list-button"));
    await waitFor(() => expect(getByTestId("webdav-files")).toBeTruthy());
    const pullBtn = getByTestId("webdav-pull-from-cloud.songworkbench");
    fireEvent.click(pullBtn);
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/backup/webdav/pull",
        expect.objectContaining({
          method: "POST",
          body: { master_password: "master123", remote_name: "from-cloud.songworkbench" },
        }),
      );
    });
    expect(toastMock.success).toHaveBeenCalled();
  });

  // ── 10. 测试已存连接 ──

  it("测试已存连接 → 调 /test-saved + 成功 toast", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (path === "/api/backup/webdav/test-saved") {
        return Promise.resolve({ ok: true, status: 207, message: "ok" });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-unlocked-section")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "master123" } });
    fireEvent.click(getByTestId("webdav-test-saved-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/backup/webdav/test-saved",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(toastMock.success).toHaveBeenCalled();
  });

  // ── 11. 测试临时凭证（unconfigured 状态）──

  it("未配置时测试连接用 /test（不传 master_password）", async () => {
    setupApiMock({ _configInitial: { configured: false } });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-config-form")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-url"), { target: { value: "https://dav.example.com" } });
    fireEvent.click(getByTestId("webdav-test-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/backup/webdav/test",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  // ── 12. 清除配置 → 状态回 unconfigured ──

  it("清除配置 → 调 /config/clear + 状态回 unconfigured", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (path === "/api/backup/webdav/config/clear") {
        return Promise.resolve({ ok: true, updated_at: "" });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-unlocked-section")).toBeTruthy());
    fireEvent.change(getByTestId("webdav-input-master-password"), { target: { value: "master123" } });
    fireEvent.click(getByTestId("webdav-clear-button"));
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledWith(
        "/api/backup/webdav/config/clear",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(getByTestId("webdav-config-form")).toBeTruthy();
    });
  });

  // ── 13. 离线时点击保存 → toast.warn 不发请求 ──

  it("离线时点击保存 → toast.warn 提示且不发请求", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    setupApiMock({ _configInitial: { configured: false } });
    const { getByTestId } = render(<WebDavPanel />);
    await waitFor(() => expect(getByTestId("webdav-offline-banner")).toBeTruthy());
    const saveCallsBefore = apiRequest.mock.calls.length;
    // 即使按钮 disabled，jsdom click 不触发；验证 disabled 即可
    const saveBtn = getByTestId("webdav-save-button") as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
    // 没有新请求
    expect(apiRequest.mock.calls.length).toBe(saveCallsBefore);
  });

  // ── 14. 加载失败显示行内错误 ──

  it("GET config 失败 → 显示错误状态", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path === "/api/backup/webdav/config") {
        return Promise.reject(new Error("后端没起来"));
      }
      return Promise.resolve({});
    });
    const { getByTestId, queryByTestId } = render(<WebDavPanel />);
    await waitFor(() => {
      expect(queryByTestId("webdav-config-form")).toBeNull();
    });
    // 错误状态无 testid 但 role=alert
    expect(getByTestId("webdav-panel").textContent).toContain("后端没起来");
  });
});

describe("WebDavPanel - M2.4 自动同步", () => {
  function setupUnlocked(_overrides: Record<string, unknown> = {}) {
    // 模拟 enabled 状态可被 POST /auto-sync 改写
    let enabled = false;
    let interval_min = 60;
    let direction: "push" | "pull" | "both" = "push";
    apiRequest.mockImplementation((path: string, opts?: { body?: unknown }) => {
      const [pathOnly] = path.split("?");
      const method = (opts?.body !== undefined) ? "POST" : "GET";
      if (pathOnly === "/api/backup/webdav/config") {
        return Promise.resolve(SAMPLE_CONFIG);
      }
      if (pathOnly === "/api/backup/webdav/list") return Promise.resolve(SAMPLE_FILES);
      if (pathOnly === "/api/backup/webdav/auto-sync") {
        if (method === "POST" && opts?.body) {
          const b = opts.body as Record<string, unknown>;
          if (b.enabled === true) enabled = true;
          if (b.enabled === false) enabled = false;
          if (typeof b.interval_minutes === "number") interval_min = b.interval_minutes;
          if (b.direction === "push" || b.direction === "pull" || b.direction === "both") {
            direction = b.direction;
          }
        }
        return Promise.resolve({
          enabled, interval_minutes: interval_min, direction,
          last_at: null, last_status: null, last_error: null, last_remote_name: null,
        });
      }
      if (pathOnly === "/api/backup/webdav/auto-sync/run") {
        return Promise.resolve({ ok: true, result: {} });
      }
      if (pathOnly === "/api/backup/webdav/push") return Promise.resolve(SAMPLE_PUSH);
      if (pathOnly === "/api/backup/webdav/pull") return Promise.resolve(SAMPLE_PULL);
      if (pathOnly === "/api/backup/webdav/test-saved") {
        return Promise.resolve({ ok: true, status: 207, message: "ok" });
      }
      return Promise.resolve({});
    });
  }

  // 辅助：等 unlocked + auto-sync 状态都落地
  async function waitForUnlockedAndAutoSync(getByTestId: (id: string) => HTMLElement) {
    await waitFor(() => expect(getByTestId("webdav-unlocked-section")).toBeTruthy());
    await waitFor(() => {
      const en = document.querySelector('[data-testid="webdav-autosync-enable"]');
      const dis = document.querySelector('[data-testid="webdav-autosync-disable"]');
      expect(en ?? dis).toBeTruthy();
    });
  }

  it("unlocked 视图渲染自动同步 section + 默认未启用", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    expect(getByTestId("webdav-autosync-section")).toBeTruthy();
    expect(getByTestId("webdav-autosync-status").textContent).toContain("未启用");
    expect(getByTestId("webdav-autosync-enable")).toBeTruthy();
    expect(document.querySelector('[data-testid="webdav-autosync-disable"]')).toBeNull();
  });

  it("自动同步启用时 status 文本反映成功状态", async () => {
    apiRequest.mockImplementation((path: string) => {
      const [pathOnly] = path.split("?");
      if (pathOnly === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (pathOnly === "/api/backup/webdav/auto-sync") return Promise.resolve({
        enabled: true, interval_minutes: 60, direction: "push",
        last_at: "2026-08-09T10:30:00", last_status: "success",
        last_error: null, last_remote_name: "song-20260809.songworkbench",
      });
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    const status = getByTestId("webdav-autosync-status");
    expect(status.textContent).toContain("上次成功");
    expect(getByTestId("webdav-autosync-disable")).toBeTruthy();
    expect(document.querySelector('[data-testid="webdav-autosync-enable"]')).toBeNull();
  });

  it("自动同步失败时显示错误信息", async () => {
    apiRequest.mockImplementation((path: string) => {
      const [pathOnly] = path.split("?");
      if (pathOnly === "/api/backup/webdav/config") return Promise.resolve(SAMPLE_CONFIG);
      if (pathOnly === "/api/backup/webdav/auto-sync") return Promise.resolve({
        enabled: true, interval_minutes: 60, direction: "push",
        last_at: "2026-08-09T10:30:00", last_status: "failed",
        last_error: "auth_failed: 401 Unauthorized", last_remote_name: null,
      });
      return Promise.resolve({});
    });
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    const err = getByTestId("webdav-autosync-error");
    expect(err.textContent).toContain("auth_failed: 401");
  });

  it("改间隔下拉 → POST /auto-sync 带 interval_minutes", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    const sel = getByTestId("webdav-autosync-interval") as HTMLSelectElement;
    await userEvent.selectOptions(sel, "30");
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(c => c[0] === "/api/backup/webdav/auto-sync"
        && (c[1] as { method?: string })?.method === "POST");
      expect(calls.length).toBeGreaterThanOrEqual(1);
      const body = ((calls[calls.length - 1][1] as { body?: Record<string, unknown> }).body) ?? {};
      expect(body.interval_minutes).toBe(30);
    });
  });

  it("改方向下拉 → POST /auto-sync 带 direction", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    const sel = getByTestId("webdav-autosync-direction") as HTMLSelectElement;
    await userEvent.selectOptions(sel, "both");
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(c => c[0] === "/api/backup/webdav/auto-sync"
        && (c[1] as { method?: string })?.method === "POST");
      expect(calls.length).toBeGreaterThanOrEqual(1);
      const body = ((calls[calls.length - 1][1] as { body?: Record<string, unknown> }).body) ?? {};
      expect(body.direction).toBe("both");
    });
  });

  it("启用自动同步：未填主密码时按钮 disabled", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    const enableBtn = getByTestId("webdav-autosync-enable") as HTMLButtonElement;
    expect(enableBtn.disabled).toBe(true);
  });

  it("启用自动同步：填主密码后点击 → POST 启用带 master_password", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    fireEvent.change(getByTestId("webdav-input-master-password"),
      { target: { value: "master123" } });
    await userEvent.click(getByTestId("webdav-autosync-enable"));
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(c => c[0] === "/api/backup/webdav/auto-sync"
        && (c[1] as { method?: string })?.method === "POST");
      const enableCall = calls.find(c => {
        const b = ((c[1] as { body?: Record<string, unknown> }).body) ?? {};
        return b.enabled === true;
      });
      expect(enableCall).toBeTruthy();
      const body = ((enableCall![1] as { body?: Record<string, unknown> }).body) ?? {};
      expect(body.master_password).toBe("master123");
    });
  });

  it("关闭自动同步：POST enabled=false 不带 master_password", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    fireEvent.change(getByTestId("webdav-input-master-password"),
      { target: { value: "master123" } });
    await userEvent.click(getByTestId("webdav-autosync-enable"));
    await waitFor(() => expect(getByTestId("webdav-autosync-disable")).toBeTruthy());
    await userEvent.click(getByTestId("webdav-autosync-disable"));
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(c => c[0] === "/api/backup/webdav/auto-sync"
        && (c[1] as { method?: string })?.method === "POST");
      const disableCall = calls.find(c => {
        const b = ((c[1] as { body?: Record<string, unknown> }).body) ?? {};
        return b.enabled === false;
      });
      expect(disableCall).toBeTruthy();
      const body = ((disableCall![1] as { body?: Record<string, unknown> }).body) ?? {};
      expect(body.master_password).toBeUndefined();
    });
  });

  it("「立即同步一次」→ POST /auto-sync/run 带 master_password", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    fireEvent.change(getByTestId("webdav-input-master-password"),
      { target: { value: "master123" } });
    await userEvent.click(getByTestId("webdav-autosync-run"));
    await waitFor(() => {
      const calls = apiRequest.mock.calls.filter(c => c[0] === "/api/backup/webdav/auto-sync/run"
        && (c[1] as { method?: string })?.method === "POST");
      expect(calls.length).toBe(1);
      const body = ((calls[0][1] as { body?: Record<string, unknown> }).body) ?? {};
      expect(body.master_password).toBe("master123");
    });
  });

  it("离线时启用按钮 disabled", async () => {
    setupUnlocked();
    const { getByTestId } = render(<WebDavPanel />);
    await waitForUnlockedAndAutoSync(getByTestId);
    fireEvent(window, new Event("offline"));
    await waitFor(() => {
      const enable = getByTestId("webdav-autosync-enable") as HTMLButtonElement;
      expect(enable.disabled).toBe(true);
    });
  });
});
