import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_APPEARANCE, normalizeAppearance, resolveAppearance } from "../appearance.ts";

test("normalizeAppearance applies contract defaults to missing values", () => {
  assert.deepEqual(normalizeAppearance(undefined), DEFAULT_APPEARANCE);
});

test("normalizeAppearance preserves valid appearance contract values", () => {
  assert.deepEqual(normalizeAppearance({ appearanceMode: "dark", applicationAccentId: "rouge" }), {
    appearanceMode: "dark",
    applicationAccentId: "rouge",
  });
});

test("resolveAppearance only consults system preference in system mode", () => {
  assert.equal(resolveAppearance("system", true), "dark");
  assert.equal(resolveAppearance("system", false), "light");
  assert.equal(resolveAppearance("light", true), "light");
  assert.equal(resolveAppearance("dark", false), "dark");
});
