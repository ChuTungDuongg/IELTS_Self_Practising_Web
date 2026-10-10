"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactElement, type ReactNode } from "react";
import { translate } from "./translations";
import type { Locale, TranslationFunction, TranslationKey, TranslationParams } from "./types";

const STORAGE_KEY = "ielts-locale";
type LocaleContextValue = { locale: Locale; setLocale(locale: Locale): void };
const LocaleContext = createContext<LocaleContextValue>({ locale: "en", setLocale: () => undefined });

export function LocaleProvider({ children }: { children: ReactNode }): ReactElement {
  const [locale, setCurrentLocale] = useState<Locale>("en");

  useEffect(() => {
    let restored: Locale = "en";
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "en" || saved === "vi") restored = saved;
    } catch {
      // Storage is optional; SSR and the first client render always use English.
    }
    // Reconcile an external preference only after hydration preserves the server markup.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentLocale(restored);
  }, []);

  useEffect(() => { document.documentElement.lang = locale; }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setCurrentLocale(next);
    try { window.localStorage.setItem(STORAGE_KEY, next); }
    catch { /* The current document still changes when persistence is unavailable. */ }
  }, []);
  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): { locale: Locale; setLocale(locale: Locale): void } {
  return useContext(LocaleContext);
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
