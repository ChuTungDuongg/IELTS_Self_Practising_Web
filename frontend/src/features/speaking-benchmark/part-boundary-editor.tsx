import type { SpeakingDraft } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./lab.module.css";

export function PartBoundaryEditor({ draft, disabled, durationMs, onChange }: { draft: SpeakingDraft; disabled: boolean; durationMs: number; onChange(value: SpeakingDraft): void }) {
  const { t } = useTranslation();
  return <section className={styles.panel}><h2>{t("speakingLab.parts")}</h2><p className={styles.muted}>{t("speakingLab.partsHelp")}</p><fieldset className={styles.fields} disabled={disabled}>
    {(["part2_start_ms", "part3_start_ms"] as const).map((key, index) => <label className={styles.field} key={key}>{t("speakingLab.partStart", { part: index + 2 })}<input className="field" type="number" min={0.001} max={durationMs / 1000} step={0.001} value={draft[key] === null ? "" : draft[key] / 1000} onChange={e => onChange({ ...draft, [key]: e.target.value === "" ? null : Math.round(Number(e.target.value) * 1000), boundaries_verified: false })} /></label>)}
    <label className={`${styles.check} ${styles.wide}`}><input type="checkbox" checked={draft.boundaries_verified} onChange={e => onChange({ ...draft, boundaries_verified: e.target.checked })} />{t("speakingLab.confirmParts")}</label>
  </fieldset></section>;
}
