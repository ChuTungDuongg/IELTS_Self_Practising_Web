import type { SpeakingDraft, SpeakingSegment } from "@/lib/api/speaking-benchmark";
import type { AudioWindow } from "./audio-review-player";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./lab.module.css";

export function SegmentEditor({ draft, disabled, durationMs, onChange, onPlay, onSuggest }: { draft: SpeakingDraft; disabled: boolean; durationMs: number; onChange(value: SpeakingDraft): void; onPlay(windows: AudioWindow[]): void; onSuggest(): void }) {
  const { t } = useTranslation();
  function update(index: number, patch: Partial<SpeakingSegment>) { onChange({ ...draft, segments: draft.segments.map((s, i) => i === index ? { ...s, ...patch } : s) }); }
  return <section className={styles.panel}><h2>{t("speakingLab.responses")} ({draft.segments.filter(s => s.included).length})</h2>
    <p className={styles.muted}>{t("speakingLab.responsesHelp")}</p>
    <div className={styles.actions}><button className="btn btn-secondary" type="button" disabled={disabled || !draft.candidate_speaker_id} onClick={onSuggest}>{t("speakingLab.suggest")}</button><button className="btn btn-ghost" type="button" disabled={disabled || !draft.candidate_speaker_id || draft.segments.length >= 100} onClick={() => onChange({ ...draft, segments: [...draft.segments, { id: `manual-${crypto.randomUUID()}`, speaker_id: draft.candidate_speaker_id!, start_ms: 0, end_ms: Math.min(1000, durationMs), included: true, prompt_text: "", cue_points: [], prompt_verified: false, long_turn: false, silence_reviewed: false }] })}>{t("speakingLab.addWindow")}</button></div>
    <div className={styles.segments}>{draft.segments.map((segment, index) => <details className={styles.segment} key={segment.id} open={draft.segments.length <= 3 ? true : undefined}><summary>{index + 1}. {(segment.start_ms / 1000).toFixed(2)}–{(segment.end_ms / 1000).toFixed(2)} s · {segment.included ? t("speakingLab.included") : t("speakingLab.excluded")}</summary>
      <fieldset className={styles.fields} disabled={disabled}>
        <label className={styles.check}><input type="checkbox" checked={segment.included} onChange={e => update(index, { included: e.target.checked })} />{t("speakingLab.include")}</label>
        <button className="btn btn-secondary" type="button" onClick={() => onPlay([segment])}>{t("speakingLab.playWindow")}</button>
        {(["start_ms", "end_ms"] as const).map(key => <label key={key} className={styles.field}>{t(key === "start_ms" ? "speakingLab.start" : "speakingLab.end")}<input className="field" type="number" min={0} max={durationMs / 1000} step={0.001} value={segment[key] / 1000} onChange={e => update(index, { [key]: Math.round(Number(e.target.value) * 1000), prompt_verified: false, silence_reviewed: false })} /></label>)}
        <label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.question")}<textarea aria-label={t("speakingLab.question")} className="textarea-field" maxLength={10000} value={segment.prompt_text} onChange={e => update(index, { prompt_text: e.target.value, prompt_verified: false })} /></label>
        <label className={`${styles.field} ${styles.wide}`}>{t("speakingLab.cuePoints")}<textarea aria-label={t("speakingLab.cuePoints")} className="textarea-field" value={segment.cue_points.join("\n")} onChange={e => update(index, { cue_points: e.target.value.split("\n").filter(Boolean), prompt_verified: false })} /></label>
        <label className={styles.check}><input type="checkbox" checked={segment.prompt_verified} onChange={e => update(index, { prompt_verified: e.target.checked })} />{t("speakingLab.confirmPrompt")}</label>
        <label className={styles.check}><input type="checkbox" checked={segment.long_turn} onChange={e => update(index, { long_turn: e.target.checked })} />{t("speakingLab.longTurn")}</label>
        <label className={`${styles.check} ${styles.wide}`}><input type="checkbox" checked={segment.silence_reviewed} onChange={e => update(index, { silence_reviewed: e.target.checked })} />{t("speakingLab.silenceReviewed")}</label>
      </fieldset>
    </details>)}</div>
  </section>;
}
