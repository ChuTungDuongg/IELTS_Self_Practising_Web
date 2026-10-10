import { en } from "./en";
import { vi } from "./vi";
import type { Locale, TranslationKey, TranslationParams } from "./types";

export function translate(locale: Locale, key: TranslationKey, params?: TranslationParams): string {
  const message = (locale === "vi" ? vi[key] : en[key]) ?? en[key];
  return message.replace(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g, (token, name: string) =>
    params && Object.hasOwn(params, name) ? String(params[name]) : token,
  );
}

export const moduleTranslationKeys: Record<"READING" | "LISTENING" | "WRITING", TranslationKey> = {
  READING: "common.reading", LISTENING: "common.listening", WRITING: "common.writing",
};

export const statusTranslationKeys: Readonly<Record<string, TranslationKey>> = {
  DRAFT: "common.draft", PUBLISHED: "common.published", ARCHIVED: "common.archived",
  IN_PROGRESS: "common.inProgress", PAUSED: "common.paused", SUBMITTED: "common.submitted",
  AUTO_SUBMITTED: "common.autoSubmitted", INTERRUPTED: "common.interrupted", ABANDONED: "common.abandoned",
};
