/// R9.3 capo 工具测试
import { describe, expect, it } from "vitest";
import { transposeKey, clampCapo } from "./capo";

describe("transposeKey", () => {
  it("capo=0 → 返回原 Key", () => {
    expect(transposeKey("C", 0)).toBe("C");
    expect(transposeKey("G", 0)).toBe("G");
  });

  it("C + Capo 2 = D（最常见情况）", () => {
    expect(transposeKey("C", 2)).toBe("D");
  });

  it("G + Capo 2 = A", () => {
    expect(transposeKey("G", 2)).toBe("A");
  });

  it("D + Capo 2 = E", () => {
    expect(transposeKey("D", 2)).toBe("E");
  });

  it("Em (小调) + Capo 3 = Gm", () => {
    expect(transposeKey("Em", 3)).toBe("Gm");
  });

  it("Db (降号) → 升 1 半音 = D", () => {
    expect(transposeKey("Db", 1)).toBe("D");
  });

  it("空 key → 返回空", () => {
    expect(transposeKey("", 2)).toBe("");
  });

  it("未知 key → 返回原 key", () => {
    expect(transposeKey("H", 2)).toBe("H"); // H 不在 SHARP_KEYS
  });

  it("Capo 12 = 一个八度 → 同名 Key", () => {
    expect(transposeKey("C", 12)).toBe("C");
    expect(transposeKey("G", 12)).toBe("G");
  });

  it("B + Capo 2 = C# (跨过 C 的边界)", () => {
    expect(transposeKey("B", 2)).toBe("C#");
  });
});

describe("clampCapo", () => {
  it("0-12 范围内不变", () => {
    expect(clampCapo(0)).toBe(0);
    expect(clampCapo(5)).toBe(5);
    expect(clampCapo(12)).toBe(12);
  });

  it("负数 → 0", () => {
    expect(clampCapo(-1)).toBe(0);
    expect(clampCapo(-100)).toBe(0);
  });

  it("大于 12 → 12", () => {
    expect(clampCapo(13)).toBe(12);
    expect(clampCapo(100)).toBe(12);
  });

  it("小数 → 四舍五入", () => {
    expect(clampCapo(2.4)).toBe(2);
    expect(clampCapo(2.6)).toBe(3);
  });

  it("NaN → 0", () => {
    expect(clampCapo(NaN)).toBe(0);
  });
});
