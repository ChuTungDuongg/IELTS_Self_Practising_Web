"use client";

import { useCallback, useRef, useState } from "react";
import { SettingsIcon } from "@/components/ui/icons";
import { PersonalizationDialog } from "@/features/personalization/personalization-dialog";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./practice-runner.module.css";

export function PracticeTools({ compact = false, mobileOnly = false, mode = "all" }: { compact?: boolean; mobileOnly?: boolean; mode?: "all" | "highlight" | "settings" }) {
  const { t } = useTranslation();
  const [settings, setSettings] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const closeSettings = useCallback(() => setSettings(false), []);
  return <aside className={`${styles.tools} ${compact ? styles.compactTools : ""} ${mobileOnly ? styles.mobileTools : ""}`} aria-label={t("practiceUi.tools")}>
    {mode !== "settings" ? <details><summary><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m5 15 9-11 5 4-9 11H5ZM14 4l5 4M4 21h15" /></svg><span>{t("runner.highlight")}</span></summary><p>{t("practiceUi.highlightHint")}</p></details> : null}
    {mode !== "highlight" ? <button ref={trigger} type="button" onClick={() => setSettings(true)}><SettingsIcon width={20} height={20} /><span>{t("practiceUi.settings")}</span></button> : null}
    <PersonalizationDialog open={settings} onClose={closeSettings} returnFocusRef={trigger} />
  </aside>;
}
