"use client";

import { useLayoutEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";

type Theme = "light" | "dark";
const STORAGE_KEY = "ielts-theme";

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  const { t } = useTranslation();
  useLayoutEffect(() => {
    // Reconcile the bootstrapped root only after deterministic server/client markup.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(currentTheme());
  }, []);

  function toggle() {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setTheme(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The theme still changes for this document even if persistence is unavailable.
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="theme-toggle"
      aria-label={t(theme === "dark" ? "theme.useLight" : "theme.useDark")}
      title={t(theme === "dark" ? "theme.useLight" : "theme.useDark")}
    >
      <span className="theme-light-label" aria-hidden="true"><span className="theme-icon">☾</span><span className="theme-text">{t("theme.useDark")}</span></span>
      <span className="theme-dark-label" aria-hidden="true"><span className="theme-icon">☀</span><span className="theme-text">{t("theme.useLight")}</span></span>
    </button>
  );
}
