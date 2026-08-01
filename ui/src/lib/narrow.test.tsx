/// R4.1.7 narrow helper 单元测试。
import { describe, expect, it } from "vitest";
import {
  asRecord, asString, asNumber, asBoolean, asStringArray,
  narrowWith, narrowUnknown, asStringOr, asNumberOr,
} from "./narrow";

describe("asRecord", () => {
  it("plain object → Record", () => {
    expect(asRecord({ a: 1 })).toEqual({ a: 1 });
  });
  it("null → null", () => {
    expect(asRecord(null)).toBeNull();
  });
  it("undefined → null", () => {
    expect(asRecord(undefined)).toBeNull();
  });
  it("string → null", () => {
    expect(asRecord("hello")).toBeNull();
  });
  it("array → null", () => {
    expect(asRecord([1, 2, 3])).toBeNull();
  });
  it("nested object → 仍是 Record", () => {
    expect(asRecord({ a: { b: 1 } })).toEqual({ a: { b: 1 } });
  });
});

describe("asString", () => {
  it("string → string", () => {
    expect(asString({ a: "hi" }, "a")).toBe("hi");
  });
  it("number → null", () => {
    expect(asString({ a: 1 }, "a")).toBeNull();
  });
  it("missing key → null", () => {
    expect(asString({ a: "x" }, "b")).toBeNull();
  });
  it("null value → null", () => {
    expect(asString({ a: null }, "a")).toBeNull();
  });
});

describe("asNumber", () => {
  it("number → number", () => {
    expect(asNumber({ a: 42 }, "a")).toBe(42);
  });
  it("string → null", () => {
    expect(asNumber({ a: "42" }, "a")).toBeNull();
  });
  it("NaN → null", () => {
    expect(asNumber({ a: NaN }, "a")).toBeNull();
  });
  it("Infinity → null", () => {
    expect(asNumber({ a: Infinity }, "a")).toBeNull();
  });
  it("0 → 0 (不误杀)", () => {
    expect(asNumber({ a: 0 }, "a")).toBe(0);
  });
});

describe("asBoolean", () => {
  it("true → true", () => {
    expect(asBoolean({ a: true }, "a")).toBe(true);
  });
  it("false → false (不误杀)", () => {
    expect(asBoolean({ a: false }, "a")).toBe(false);
  });
  it("truthy string → null", () => {
    expect(asBoolean({ a: "true" }, "a")).toBeNull();
  });
});

describe("asStringArray", () => {
  it("全 string 数组 → array", () => {
    expect(asStringArray({ a: ["x", "y"] }, "a")).toEqual(["x", "y"]);
  });
  it("空数组 → []", () => {
    expect(asStringArray({ a: [] }, "a")).toEqual([]);
  });
  it("含 number → null", () => {
    expect(asStringArray({ a: ["x", 1] }, "a")).toBeNull();
  });
  it("非数组 → null", () => {
    expect(asStringArray({ a: "x" }, "a")).toBeNull();
  });
});

describe("narrowWith", () => {
  it("validator 通过 → 返回", () => {
    const isPositive = (n: unknown) => typeof n === "number" && n > 0 ? n : null;
    expect(narrowWith({ a: 5 }, "a", isPositive)).toBe(5);
  });
  it("validator 拒绝 → null", () => {
    const isPositive = (n: unknown) => typeof n === "number" && n > 0 ? n : null;
    expect(narrowWith({ a: -1 }, "a", isPositive)).toBeNull();
  });
  it("missing key → null", () => {
    const isNumber = (v: unknown) => typeof v === "number" ? v : null;
    expect(narrowWith({ a: 1 }, "b", isNumber)).toBeNull();
  });
});

describe("narrowUnknown", () => {
  const isStr = (v: unknown) => typeof v === "string" ? v : null;
  it("validator 通过 → 返回", () => {
    expect(narrowUnknown("hi", isStr)).toBe("hi");
  });
  it("validator 拒绝 → null", () => {
    expect(narrowUnknown(42, isStr)).toBeNull();
  });
});

describe("asStringOr / asNumberOr fallback", () => {
  it("asStringOr: missing → fallback", () => {
    expect(asStringOr({ a: "x" }, "b", "fallback")).toBe("fallback");
  });
  it("asStringOr: wrong type → fallback", () => {
    expect(asStringOr({ a: 1 }, "a", "fallback")).toBe("fallback");
  });
  it("asNumberOr: NaN → fallback", () => {
    expect(asNumberOr({ a: NaN }, "a", 99)).toBe(99);
  });
  it("asNumberOr: 0 → 0 (不误杀)", () => {
    expect(asNumberOr({ a: 0 }, "a", 99)).toBe(0);
  });
});
