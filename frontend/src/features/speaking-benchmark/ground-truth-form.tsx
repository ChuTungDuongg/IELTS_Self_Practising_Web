"use client";

import { useState } from "react";
import { saveSpeakingLabels, type SpeakingLabels } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import styles from "./lab.module.css";

export function GroundTruthForm({ sampleId, initial, disabled = false, onSaved, onDirty }: { sampleId: string; initial: SpeakingLabels; disabled?: boolean; onSaved(value: SpeakingLabels): void | Promise<void>; onDirty(value: boolean): void }) {
  const { t } = useTranslation(); const [value, setValue] = useState(initial); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [saved, setSaved] = useState(initial.revision > 0);
  function change(patch: Partial<SpeakingLabels>) { setValue({ ...value, ...patch }); setSaved(false); onDirty(true); }
  return <form className={styles.panel} onSubmit={async event => { event.preventDefault(); onDirty(true); setBusy(true); setError(""); try { const result = await saveSpeakingLabels(sampleId, value); setValue(result); await onSaved(result); onDirty(false); setSaved(true); } catch (failure) { setError(labError(failure, t)); } finally { setBusy(false); } }}>
    <h2>{t("speakingLab.groundTruth")}</h2><p>{t(Object.values(value.bands).every(v => v === null) ? "speakingLab.unlabelled" : value.verified ? "speakingLab.verified" : "speakingLab.unverified")}</p><p className={styles.muted}>{t("speakingLab.labelsHelp")}</p>
    <fieldset className={styles.fields} disabled={busy || disabled}>
      <div className={`${styles.scoreFields} ${styles.wide}`}>{(["fc", "lr", "gra", "pr", "overall"] as const).map(key => <label className={styles.field} key={key}>{key === "overall" ? t("speakingLab.overall") : key.toUpperCase()}<select className="select-field" value={value.bands[key] ?? ""} onChange={e => change({ bands: { ...value.bands, [key]: e.target.value === "" ? null : Number(e.target.value) } })}><option value="">—</option>{Array.from({ length: 19 }, (_, i) => i / 2).map(n => <option key={n} value={n}>{n.toFixed(1)}</option>)}</select></label>)}</div>
      <label className={styles.field}>{t("speakingLab.provenance")}<select className="select-field" value={value.provenance} onChange={e => change({ provenance: e.target.value as SpeakingLabels["provenance"], verified: false })}><option value="unverified">{t("speakingLab.unverified")}</option><option value="human_examiner">{t("speakingLab.humanExaminer")}</option><option value="published_human_assessment">{t("speakingLab.publishedHuman")}</option></select></label>
      <label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.reference")}<input className="field" maxLength={2000} value={value.reference} required={value.verified} onChange={e => change({ reference: e.target.value, verified: false })} /></label>
      <label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.examiner")}<input className="field" maxLength={500} value={value.examiner} onChange={e => change({ examiner: e.target.value })} /></label>
      <label className={`${styles.check} ${styles.wide}`}><input type="checkbox" disabled={value.provenance === "unverified" || !value.reference.trim()} checked={value.verified} onChange={e => change({ verified: e.target.checked })} />{t("speakingLab.confirmHuman")}</label>
      <label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.notes")}<textarea className="textarea-field" maxLength={5000} value={value.notes} onChange={e => change({ notes: e.target.value })} /></label>
    </fieldset>
    {error && <p role="alert" className="notice notice-error">{error}</p>}{saved && <p role="status">{t("common.saved")}</p>}
    <button className="btn btn-secondary" disabled={busy || disabled}>{t(busy ? "common.saving" : "speakingLab.saveLabels")}</button>
  </form>;
}
