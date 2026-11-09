"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality.module.css";

export function GateSourceSelector({ title, kind, onKind, fingerprint, onFingerprint, experimentId, onExperimentId, variantKey, onVariantKey }: {
  title: string;
  kind: "GRADING" | "EXPERIMENT";
  onKind: (value: "GRADING" | "EXPERIMENT") => void;
  fingerprint: string;
  onFingerprint: (value: string) => void;
  experimentId: string;
  onExperimentId: (value: string) => void;
  variantKey: string;
  onVariantKey: (value: string) => void;
}) {
  const { t } = useTranslation();
  return <fieldset className={styles.sourceFields}>
    <legend>{title}</legend>
    <label>{t("speakingUx.selectorKind")}
      <select className="field" value={kind} onChange={event => onKind(event.target.value as typeof kind)}>
        <option value="GRADING">{t("speakingUx.gradingSource")}</option>
        <option value="EXPERIMENT">{t("speakingUx.experimentSource")}</option>
      </select>
    </label>
    {kind === "GRADING" ? <label>{t("speakingUx.configFingerprint")}
      <input className="field" value={fingerprint} onChange={event => onFingerprint(event.target.value)} />
    </label> : <>
      <label>{t("speakingUx.experimentId")}<input className="field" value={experimentId} onChange={event => onExperimentId(event.target.value)} /></label>
      <label>{t("speakingUx.variantKey")}<input className="field" value={variantKey} onChange={event => onVariantKey(event.target.value)} /></label>
    </>}
  </fieldset>;
}
