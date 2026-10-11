"use client";

import { usePersonalization } from "@/features/personalization/personalization-provider";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { MoonIcon, SunIcon } from "./icons";

export function ThemeToggle() {
  const { appearance, setAppearance, canUpdate } = usePersonalization();
  const theme = appearance === "DARK" ? "dark" : "light";
  const { t } = useTranslation();

  return (
    <button
      type="button"
      onClick={() => setAppearance(appearance === "DARK" ? "LIGHT" : "DARK")}
      disabled={!canUpdate}
      className="theme-toggle"
      aria-label={t(theme === "dark" ? "theme.useLight" : "theme.useDark")}
      title={t(theme === "dark" ? "theme.useLight" : "theme.useDark")}
    >
      <span className="theme-light-label" aria-hidden="true"><MoonIcon className="theme-icon" width="18" height="18" /><span className="theme-text">{t("theme.useDark")}</span></span>
      <span className="theme-dark-label" aria-hidden="true"><SunIcon className="theme-icon" width="18" height="18" /><span className="theme-text">{t("theme.useLight")}</span></span>
    </button>
  );
}
