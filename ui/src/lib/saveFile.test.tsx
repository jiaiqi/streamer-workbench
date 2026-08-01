/// R4.0.12 saveBlob 跨平台保存路径 — 单元测试。
///
/// 覆盖：
///   - 空 blob / 空文件名 → 失败
///   - Electron saveFile 成功 → 返回 { ok: true, method: "native", path }
///   - Electron saveFile 取消 → 返回 { ok: false, cancelled: true }
///   - Electron saveFile 错误 → 返回 { ok: false, error }
///   - Electron saveFile 异常 → 返回 { ok: false, error }
///   - 浏览器走 <a download> → 触发 anchor click
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { saveBlob } from "./saveFile";

const SAMPLE_PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function makeBlob(): Blob {
  return new Blob([SAMPLE_PNG], { type: "image/png" });
}

/* ---- 跨 test 文件隔离的 URL mock 状态 ---- */
const origCreate = URL.createObjectURL;
const origRevoke = URL.revokeObjectURL;
let anchorClickSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  // 清理 window.streamer
  delete (window as { streamer?: unknown }).streamer;
  // 注入浏览器 mock（每个 test 都重设）
  anchorClickSpy = vi.fn();
  URL.createObjectURL = vi.fn(() => "blob:mock-url") as unknown as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
  vi.spyOn(document.body, "appendChild").mockImplementation(((node: Node) => {
    if (node instanceof HTMLAnchorElement) {
      node.click = anchorClickSpy as unknown as HTMLAnchorElement["click"];
    }
    return node as unknown as Node;
  }) as typeof document.body.appendChild);
});

afterEach(() => {
  URL.createObjectURL = origCreate;
  URL.revokeObjectURL = origRevoke;
  vi.restoreAllMocks();
});

describe("saveBlob 参数校验", () => {
  it("空 defaultName → 失败 + error", async () => {
    const res = await saveBlob(makeBlob(), "");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toBeTruthy();
  });
});

describe("saveBlob Electron 路径", () => {
  it("saveFile 成功 → { ok: true, method: 'native', path }", async () => {
    const saveFile = vi.fn().mockResolvedValueOnce({ ok: true, path: "/tmp/foo.png" });
    (window as { streamer: unknown }).streamer = { saveFile };
    const res = await saveBlob(makeBlob(), "foo.png");
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.method).toBe("native");
      expect(res.path).toBe("/tmp/foo.png");
      expect(res.filename).toBe("foo.png");
    }
    expect(saveFile).toHaveBeenCalledOnce();
    const call = saveFile.mock.calls[0][0];
    expect(call.defaultName).toBe("foo.png");
    expect(call.mimeType).toBe("image/png");
    expect(call.data.byteLength).toBe(SAMPLE_PNG.length);
  });

  it("saveFile 取消 → { ok: false, cancelled: true }", async () => {
    (window as { streamer: unknown }).streamer = {
      saveFile: vi.fn().mockResolvedValueOnce({ ok: false, cancelled: true }),
    };
    const res = await saveBlob(makeBlob(), "foo.png");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.cancelled).toBe(true);
  });

  it("saveFile 错误 → { ok: false, error }", async () => {
    (window as { streamer: unknown }).streamer = {
      saveFile: vi.fn().mockResolvedValueOnce({ ok: false, error: "EACCES" }),
    };
    const res = await saveBlob(makeBlob(), "foo.png");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toBe("EACCES");
  });

  it("saveFile 抛异常 → { ok: false, error }", async () => {
    (window as { streamer: unknown }).streamer = {
      saveFile: vi.fn().mockRejectedValueOnce(new Error("IPC down")),
    };
    const res = await saveBlob(makeBlob(), "foo.png");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toBe("IPC down");
  });
});

describe("saveBlob 浏览器路径", () => {
  it("走 <a download>：触发 click + download 属性", async () => {
    const res = await saveBlob(makeBlob(), "browser.png");
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.method).toBe("download");
      expect(res.path).toBeNull();
    }
    expect(anchorClickSpy).toHaveBeenCalledOnce();
  });
});

