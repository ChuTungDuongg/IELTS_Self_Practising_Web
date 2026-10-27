"use client";

import { useCallback, type ReactElement, type ReactNode } from "react";
import { PersonalizationProvider, usePersonalizationLocale } from "@/features/personalization/personalization-provider";
import { translate } from "./translations";
import type { Locale, TranslationFunction, TranslationKey, TranslationParams } from "./types";

// Compatibility wrapper for isolated consumers; there is no separate locale state.
export function LocaleProvider({ children }: { children: ReactNode }): ReactElement {
  return <PersonalizationProvider>{children}</PersonalizationProvider>;
}

export function useLocale(): { locale: Locale; setLocale(locale: Locale): void } {
  return usePersonalizationLocale();
}

export function useTranslation(): { t: TranslationFunction } {
  const { locale } = useLocale();
  const t = useCallback<TranslationFunction>((key, params) => translate(locale, key, params), [locale]);
  return { t };
}

export function UiText({ message, params }: { message: TranslationKey; params?: TranslationParams }): ReactElement {
  const { t } = useTranslation();
  return <>{t(message, params)}</>;
}
