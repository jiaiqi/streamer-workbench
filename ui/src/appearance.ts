import type { AppearanceMode, AppearanceSettings, ApplicationAccentId } from "./types";

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  appearanceMode: "system",
  applicationAccentId: "bambooMoon",
};

export const APPEARANCE_OPTIONS: ReadonlyArray<{ id: AppearanceMode; label: string; description: string }> = [
  { id: "system", label: "跟随系统", description: "随设备明暗自动切换" },
  { id: "light", label: "画廊白", description: "适合日间整理与长时间阅读" },
  { id: "dark", label: "暗色舞台", description: "适合直播间与暗光环境" },
];

export const ACCENT_OPTIONS: ReadonlyArray<{ id: ApplicationAccentId; label: string; light: string; dark: string }> = [
  { id: "bambooMoon", label: "竹月青", light: "#287D69", dark: "#49B89C" },
  { id: "rainSky", label: "雨过天青", light: "#356A8A", dark: "#6FA4C5" },
  { id: "distantMountain", label: "远山黛", light: "#465E65", dark: "#879AA0" },
  { id: "rouge", label: "胭脂红", light: "#A13D50", dark: "#D77A8B" },
  { id: "begonia", label: "海棠褐", light: "#9A4F36", dark: "#D78869" },
  { id: "wisteria", label: "藤萝紫", light: "#66528A", dark: "#9B88C1" },
  { id: "amber", label: "琥珀金", light: "#8A5A16", dark: "#D0A04D" },
  { id: "pineFlower", label: "松花绿", light: "#5D6F32", dark: "#98AA67" },
];

const accentIds = new Set(ACCENT_OPTIONS.map(option => option.id));

export function normalizeAppearance(value: Partial<AppearanceSettings> | null | undefined): AppearanceSettings {
  const appearanceMode = value?.appearanceMode;
  const applicationAccentId = value?.applicationAccentId;
  return {
    appearanceMode: appearanceMode === "light" || appearanceMode === "dark" || appearanceMode === "system"
      ? appearanceMode
      : DEFAULT_APPEARANCE.appearanceMode,
    applicationAccentId: applicationAccentId && accentIds.has(applicationAccentId)
      ? applicationAccentId
      : DEFAULT_APPEARANCE.applicationAccentId,
  };
}

export function resolveAppearance(mode: AppearanceMode, systemDark: boolean): "light" | "dark" {
  return mode === "system" ? (systemDark ? "dark" : "light") : mode;
}
