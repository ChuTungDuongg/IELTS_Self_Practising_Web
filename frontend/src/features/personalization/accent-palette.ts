import type { TranslationKey } from "@/lib/i18n/types";

export const accentPresets = [
  "PURPLE", "INDIGO", "BLUE", "CYAN", "EMERALD", "GREEN", "AMBER", "ORANGE", "RED", "PINK",
] as const;
export type AccentColor = typeof accentPresets[number];

export function isAccentColor(value: unknown): value is AccentColor {
  return typeof value === "string" && accentPresets.some(preset => preset === value);
}

export function accentLabelKey(accent: AccentColor): TranslationKey {
  return `personalization.accent.${accent}`;
}
