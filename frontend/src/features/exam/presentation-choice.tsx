"use client";

import { useId } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { AttemptPresentationMode } from "./attempt-presentation";
import { PresentationThumbnail, type PresentationPreview } from "./presentation-thumbnail";
import styles from "./presentation-choice.module.css";

export function PresentationChoice({ value, onChange, disabled, module, preview }: {
  value: AttemptPresentationMode;
  onChange: (value: AttemptPresentationMode) => void;
  disabled?: boolean;
  module: "READING" | "LISTENING";
  preview?: PresentationPreview;
}) {
  const { t } = useTranslation();
  const id = useId();
  return <fieldset className={styles.choice} disabled={disabled}>
    <legend>{t("presentation.label")}</legend>
    {(["PRACTICE", "EXAM"] as const).map(mode => <label key={mode}>
      <input type="radio" name={id} checked={value === mode} onChange={() => onChange(mode)} aria-labelledby={`${id}-${mode}-label`} aria-describedby={`${id}-${mode}`} />
      <PresentationThumbnail mode={mode} module={module} preview={preview} />
      <span className={styles.caption}><strong id={`${id}-${mode}-label`}>{t(mode === "PRACTICE" ? "presentation.practice" : "presentation.exam")}</strong><span id={`${id}-${mode}`}>{t(mode === "PRACTICE" ? "presentation.practiceDescription" : "presentation.examDescription")}</span></span>
    </label>)}
  </fieldset>;
}
