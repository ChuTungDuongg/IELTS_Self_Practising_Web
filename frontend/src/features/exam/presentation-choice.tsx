"use client";

import { useId } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { AttemptPresentationMode } from "./attempt-presentation";
import styles from "./presentation-choice.module.css";

export function PresentationChoice({ value, onChange, disabled }: {
  value: AttemptPresentationMode;
  onChange: (value: AttemptPresentationMode) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  return <fieldset className={styles.choice} disabled={disabled}>
    <legend>{t("presentation.label")}</legend>
    {(["PRACTICE", "EXAM"] as const).map(mode => <label key={mode}>
      <input type="radio" name={id} checked={value === mode} onChange={() => onChange(mode)} aria-labelledby={`${id}-${mode}-label`} aria-describedby={`${id}-${mode}`} />
      <span><strong id={`${id}-${mode}-label`}>{t(mode === "PRACTICE" ? "presentation.practice" : "presentation.exam")}</strong><span id={`${id}-${mode}`}>{t(mode === "PRACTICE" ? "presentation.practiceDescription" : "presentation.examDescription")}</span></span>
    </label>)}
  </fieldset>;
}
