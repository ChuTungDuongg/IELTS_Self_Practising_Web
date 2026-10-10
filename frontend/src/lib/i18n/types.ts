import type { en } from "./en";

export type Locale = "en" | "vi";
export type TranslationKey = keyof typeof en;
export type TranslationDictionary = Record<TranslationKey, string>;
export type TranslationParams = Record<string, string | number>;
export type TranslationFunction = (key: TranslationKey, params?: TranslationParams) => string;
