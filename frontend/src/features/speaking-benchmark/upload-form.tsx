"use client";

import { useState } from "react";
import { uploadSpeakingSample, type SpeakingAvailability, type SpeakingSample } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import styles from "./lab.module.css";

export function SpeakingUploadForm({ available, onUploaded }: { available: SpeakingAvailability; onUploaded(sample: SpeakingSample): void }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  return <form className={styles.panel} onSubmit={async event => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const file = (form.elements.namedItem("audio") as HTMLInputElement).files?.[0];
    if (!data.get("rights")) { setError(t("speakingLab.rights")); return; }
    if (!(file instanceof File) || !file.size || file.size > available.max_bytes) { setError(t("speakingLab.uploadBounds")); return; }
    setBusy(true); setError("");
    try { const sample = await uploadSpeakingSample(file, { code: String(data.get("code")), candidate_id: String(data.get("candidate_id")), split: data.get("split") === "HOLDOUT" ? "HOLDOUT" : "DEV", source_note: String(data.get("source_note")), rights_confirmed: true }); form.reset(); onUploaded(sample); }
    catch (failure) { setError(labError(failure, t)); } finally { setBusy(false); }
  }}>
    <h2>{t("speakingLab.upload")}</h2><p className={styles.muted}>{t("speakingLab.uploadHelp", { mb: Math.floor(available.max_bytes / 1024 ** 2), minutes: Math.floor(available.max_duration_ms / 60000) })}</p>
    <fieldset disabled={busy} className={`${styles.fields} ${styles.uploadFields}`}>
      <label className={styles.field}>{t("speakingLab.code")}<input className="field" name="code" required maxLength={80} pattern="[\w .-]+" /></label>
      <label className={styles.field}>{t("speakingLab.candidateId")}<input className="field" name="candidate_id" maxLength={120} /></label>
      <label className={styles.field}>{t("speakingLab.split")}<select className="select-field" name="split"><option value="DEV">DEV</option><option value="HOLDOUT">HOLDOUT</option></select></label>
      <label className={styles.field}>{t("speakingLab.audioFile")}<input className="field" name="audio" type="file" accept="audio/mpeg,audio/wav,.mp3,.wav" required /></label>
      <label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.source")}<textarea className="textarea-field" name="source_note" required maxLength={2000} /></label>
      <label className={`${styles.check} ${styles.wide}`}><input name="rights" type="checkbox" required />{t("speakingLab.rights")}</label>
    </fieldset>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <button className="btn btn-primary" disabled={busy}>{t(busy ? "speakingLab.uploading" : "speakingLab.upload")}</button>
  </form>;
}
