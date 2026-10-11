"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getPreferences, updatePreferences, type Preferences, type PreferencesUpdate } from "@/lib/api/preferences";
import type { Locale } from "@/lib/i18n/types";
import { isAccentColor, type AccentColor } from "./accent-palette";

const defaults: Preferences = { accent_color: "PURPLE", appearance: "LIGHT", locale: "EN" };
type PersonalizationState = {
  accentColor: AccentColor;
  appearance: Preferences["appearance"];
  locale: Locale;
  loading: boolean;
  saving: boolean;
  canUpdate: boolean;
  error: "load" | "save" | null;
  setAccentColor(value: AccentColor): void;
  setAppearance(value: Preferences["appearance"]): void;
  setLocale(value: Locale): void;
  synchronizeAccount(userId: string | null | undefined): void;
  retry(): void;
};
const PersonalizationContext = createContext<PersonalizationState>({
  accentColor: "PURPLE", appearance: "LIGHT", locale: "en",
  loading: false, saving: false, canUpdate: true, error: null,
  setAccentColor: () => undefined, setAppearance: () => undefined, setLocale: () => undefined,
  synchronizeAccount: () => undefined, retry: () => undefined,
});

function readCache(): Preferences {
  const result = { ...defaults };
  try {
    const storage = window.localStorage;
    const accent = storage.getItem("ielts-accent");
    const theme = storage.getItem("ielts-theme");
    const locale = storage.getItem("ielts-locale");
    if (isAccentColor(accent)) result.accent_color = accent;
    if (theme === "dark" || (theme === null && document.documentElement.dataset.theme === "dark")) result.appearance = "DARK";
    if (locale === "vi") result.locale = "VI";
  } catch { /* Storage is optional, including a throwing storage getter. */ }
  return result;
}

export function PersonalizationProvider({ children }: { children: React.ReactNode }) {
  // SSR and the first client render are deterministic. Restore only after mount.
  const [values, setValues] = useState<Preferences>(defaults);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [canUpdate, setCanUpdate] = useState(true);
  const [error, setError] = useState<PersonalizationState["error"]>(null);
  const current = useRef(defaults);
  const confirmed = useRef(defaults);
  const account = useRef<string | null | undefined>(undefined);
  const ready = useRef(false);
  const pending = useRef<PreferencesUpdate>({});
  const generation = useRef(0);
  const worker = useRef<number | null>(null);
  const requests = useRef<AbortController | null>(null);
  const mounted = useRef(false);

  const apply = useCallback((next: Preferences) => {
    current.current = next;
    setValues(next);
    const root = document.documentElement;
    root.dataset.accent = next.accent_color.toLowerCase();
    root.dataset.theme = next.appearance === "DARK" ? "dark" : "light";
    root.lang = next.locale === "VI" ? "vi" : "en";
    try {
      window.localStorage.setItem("ielts-accent", next.accent_color);
      window.localStorage.setItem("ielts-theme", root.dataset.theme);
      window.localStorage.setItem("ielts-locale", root.lang);
    } catch { /* Document state still works when persistence is blocked. */ }
  }, []);

  useEffect(() => {
    mounted.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    apply(readCache());
    return () => { mounted.current = false; generation.current += 1; requests.current?.abort(); account.current = undefined; };
  }, [apply]);

  const synchronizeAccount = useCallback((userId: string | null | undefined) => {
    if (account.current === userId) return;
    requests.current?.abort();
    requests.current = null;
    account.current = userId;
    const version = ++generation.current;
    pending.current = {};
    ready.current = false;
    worker.current = null;
    setError(null);
    setSaving(false);
    setLoading(typeof userId === "string");
    setCanUpdate(typeof userId !== "string");
    if (typeof userId !== "string") return;
    const controller = new AbortController();
    requests.current = controller;
    getPreferences(controller.signal).then(result => {
      if (!mounted.current || version !== generation.current) return;
      confirmed.current = result;
      ready.current = true;
      apply(result);
      setCanUpdate(true);
    }).catch(() => {
      if (mounted.current && version === generation.current) setError("load");
    }).finally(() => {
      if (mounted.current && version === generation.current) setLoading(false);
    });
  }, [apply]);

  const flush = useCallback(async () => {
    const version = generation.current;
    if (worker.current === version) return;
    worker.current = version;
    setSaving(true);
    try {
      while (Object.keys(pending.current).length && ready.current && typeof account.current === "string") {
        const update = pending.current;
        pending.current = {};
        try {
          const result = await updatePreferences(update, requests.current?.signal);
          if (!mounted.current || version !== generation.current) return;
          confirmed.current = result;
          setError(null);
          apply({ ...result, ...pending.current });
        } catch {
          if (!mounted.current || version !== generation.current) return;
          // Roll back only failed fields; retain newer queued selections.
          apply({ ...confirmed.current, ...pending.current });
          setError("save");
        }
      }
    } finally {
      if (mounted.current && version === generation.current) {
        worker.current = null;
        setSaving(false);
      }
    }
  }, [apply]);

  const update = useCallback((patch: PreferencesUpdate) => {
    if (typeof account.current === "string" && !ready.current) return;
    apply({ ...current.current, ...patch });
    if (typeof account.current !== "string") return;
    pending.current = { ...pending.current, ...patch };
    void flush();
  }, [apply, flush]);

  const setAccentColor = useCallback((accent_color: AccentColor) => update({ accent_color }), [update]);
  const setAppearance = useCallback((appearance: Preferences["appearance"]) => update({ appearance }), [update]);
  const setLocale = useCallback((locale: Locale) => update({ locale: locale === "vi" ? "VI" : "EN" }), [update]);
  const retry = useCallback(() => {
    const userId = account.current;
    if (typeof userId !== "string" || worker.current !== null) return;
    account.current = undefined;
    synchronizeAccount(userId);
  }, [synchronizeAccount]);
  const value = useMemo<PersonalizationState>(() => ({
    accentColor: values.accent_color, appearance: values.appearance,
    locale: values.locale === "VI" ? "vi" : "en", loading, saving, canUpdate, error,
    setAccentColor, setAppearance, setLocale, synchronizeAccount, retry,
  }), [values, loading, saving, canUpdate, error, setAccentColor, setAppearance, setLocale, synchronizeAccount, retry]);
  return <PersonalizationContext.Provider value={value}>{children}</PersonalizationContext.Provider>;
}

export function usePersonalization() {
  return useContext(PersonalizationContext);
}
