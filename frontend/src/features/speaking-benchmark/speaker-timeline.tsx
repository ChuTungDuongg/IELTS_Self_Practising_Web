import { useState } from "react";
import type { AudioWindow } from "./audio-review-player";
import type { SpeakingDraft, SpeakingReview, SpeakerTurn } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./lab.module.css";

export function overlapWindows(turns: SpeakerTurn[]): AudioWindow[] {
  const ordered = [...turns].sort((a, b) => a.start_ms - b.start_ms); let active: SpeakerTurn[] = []; const spans: AudioWindow[] = [];
  for (const turn of ordered) { active = active.filter(t => t.end_ms > turn.start_ms); for (const other of active) if (other.speaker_id !== turn.speaker_id) spans.push({ start_ms: turn.start_ms, end_ms: Math.min(turn.end_ms, other.end_ms) }); active.push(turn); }
  const merged: AudioWindow[] = [];
  for (const span of spans.sort((a, b) => a.start_ms - b.start_ms)) { const previous = merged.at(-1); if (previous && previous.end_ms >= span.start_ms) previous.end_ms = Math.max(previous.end_ms, span.end_ms); else merged.push({ ...span }); }
  return merged;
}

export function SpeakerTimeline({ review, draft, disabled, onChange, onPlay, onSeek }: { review: SpeakingReview; draft: SpeakingDraft; disabled: boolean; onChange(draft: SpeakingDraft): void; onPlay(windows: AudioWindow[]): void; onSeek(ms: number): void }) {
  const { t } = useTranslation(); const speakers = Object.keys(draft.roles); const duration = review.diarization.duration_ms;
  const [mode, setMode] = useState<"exclusive" | "regular">("exclusive"); const [overlapOffset, setOverlapOffset] = useState(0);
  const overlaps = overlapWindows(review.diarization.regular);
  return <section className={styles.panel}>
    <h2>{t("speakingLab.speakers")}</h2><p className={styles.muted}>{t("speakingLab.speakerHelp")}</p>
    <label className={styles.field}>{t("speakingLab.timelineMode")}<select className="select-field" value={mode} onChange={e => setMode(e.target.value as "exclusive" | "regular")}><option value="exclusive">{t("speakingLab.exclusive")}</option><option value="regular">{t("speakingLab.regular")}</option></select></label>
    {speakers.map(speaker => { const turns = review.diarization[mode].filter(turn => turn.speaker_id === speaker); const path = turns.map(turn => `M${turn.start_ms / duration * 1000},8h${(turn.end_ms - turn.start_ms) / duration * 1000}v28h-${(turn.end_ms - turn.start_ms) / duration * 1000}z`).join(" "); return <div key={speaker} className={styles.lane}>
      <div><strong>{speaker}</strong><p className={styles.muted}>{t("speakingLab.suggestedRole")}: {t(`speakingLab.role.${review.role_suggestions[speaker] ?? "unknown"}`)}</p><label className={styles.field}>{t("speakingLab.role")}<select className="select-field" aria-label={`${t("speakingLab.role")} ${speaker}`} disabled={disabled} value={draft.roles[speaker]} onChange={e => {
        const role = e.target.value as SpeakingDraft["roles"][string]; const roles = { ...draft.roles, [speaker]: role };
        if (role === "candidate") for (const id of speakers) if (id !== speaker && roles[id] === "candidate") roles[id] = "unknown";
        const candidate = role === "candidate" ? speaker : draft.candidate_speaker_id === speaker ? null : draft.candidate_speaker_id;
        onChange({ ...draft, roles, candidate_speaker_id: candidate, candidate_confirmed: false });
      }}>{(["candidate", "examiner", "other", "unknown"] as const).map(role => <option key={role} value={role}>{t(`speakingLab.role.${role}`)}</option>)}</select></label></div>
      <div><button type="button" className={styles.track} style={{ width: "100%", border: 0, padding: 0, cursor: "pointer" }} aria-label={`${t("speakingLab.timeline")} ${speaker}`} onClick={event => { const rect = event.currentTarget.getBoundingClientRect(); onSeek(event.detail === 0 ? (turns[0]?.start_ms ?? 0) : Math.max(0, Math.min(duration, (event.clientX - rect.left) / rect.width * duration))); }}><svg viewBox="0 0 1000 44" preserveAspectRatio="none" width="100%" height="44" aria-hidden="true"><path d={path} fill="var(--accent)" opacity=".7" /></svg></button><button className="btn btn-ghost" type="button" onClick={() => onPlay(turns)}>{t("speakingLab.listenSpeaker")}</button></div>
    </div>; })}
    <label className={styles.check}><input type="checkbox" disabled={disabled || !draft.candidate_speaker_id} checked={draft.candidate_confirmed} onChange={e => onChange({ ...draft, candidate_confirmed: e.target.checked })} />{t("speakingLab.confirmCandidate")}</label>
    <details><summary>{t("speakingLab.overlaps")} ({overlaps.length})</summary><p className={styles.muted}>{t("speakingLab.overlapHelp")}</p>{overlaps.slice(overlapOffset, overlapOffset + 50).map((span, i) => <div key={i} className={styles.overlap}><button type="button" onClick={() => onPlay([span])}>{(span.start_ms / 1000).toFixed(2)}–{(span.end_ms / 1000).toFixed(2)} s</button></div>)}{overlaps.length > 50 && <div className={styles.actions}><button className="btn btn-secondary" type="button" disabled={overlapOffset === 0} onClick={() => setOverlapOffset(Math.max(0, overlapOffset - 50))}>{t("speakingLab.previous")}</button><button className="btn btn-secondary" type="button" disabled={overlapOffset + 50 >= overlaps.length} onClick={() => setOverlapOffset(overlapOffset + 50)}>{t("speakingLab.next")}</button></div>}</details>
  </section>;
}
