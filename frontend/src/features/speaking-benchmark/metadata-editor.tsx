import { useState } from "react";
import { patchSpeakingSample, type SpeakingSample } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import styles from "./lab.module.css";

export function SampleMetadataEditor({ sample, disabled, onDirty, onSaved }: { sample: SpeakingSample; disabled: boolean; onDirty(value: boolean): void; onSaved(value: SpeakingSample): void }) {
  const { t } = useTranslation(); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  return <details className={styles.panel}><summary>{t("speakingLab.metadata")}</summary><form onChange={() => onDirty(true)} onSubmit={async event => { event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(""); try { const saved = await patchSpeakingSample(sample.id, { code: String(data.get("code")), candidate_id: String(data.get("candidate_id")), split: data.get("split") === "HOLDOUT" ? "HOLDOUT" : "DEV", source_note: String(data.get("source_note")), rights_confirmed: true }, sample.revision); onDirty(false); onSaved(saved); } catch (failure) { setError(labError(failure, t)); } finally { setBusy(false); } }}>
    <fieldset className={styles.fields} disabled={busy || disabled}><label className={styles.field}>{t("speakingLab.code")}<input className="field" name="code" required maxLength={80} defaultValue={sample.code} /></label><label className={styles.field}>{t("speakingLab.candidateId")}<input className="field" name="candidate_id" maxLength={120} defaultValue={sample.candidate_id} /></label><label className={styles.field}>{t("speakingLab.split")}<select className="select-field" name="split" defaultValue={sample.split}><option>DEV</option><option>HOLDOUT</option></select></label><label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.source")}<textarea className="textarea-field" name="source_note" required maxLength={2000} defaultValue={sample.source_note} /></label></fieldset>{error && <p role="alert">{error}</p>}<button className="btn btn-secondary" disabled={busy || disabled}>{t("speakingLab.saveMetadata")}</button>
  </form></details>;
}
