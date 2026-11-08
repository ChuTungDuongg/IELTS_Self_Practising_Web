"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api/speaking-benchmark-research";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { AudioReviewPlayer, useSourcePlayback } from "../audio-review-player";
import { labError } from "../errors";
import styles from "./research.module.css";

export function TranscriptComparison({ experiment, latest }: { experiment: api.ResearchExperiment; latest: boolean }) {
  const { t } = useTranslation(); const [selection, setSelection] = useState(""); const [rows, setRows] = useState<api.ResearchResult[]>([]); const [error, setError] = useState(""); const [showDiff, setShowDiff] = useState(false); const playback = useSourcePlayback(); const stop = playback.stop;
  const windows = experiment.configuration.cohort.flatMap(c => c.windows.map(w => ({ ...w, cohort: c, key: `${c.sample_id}:${w.id}` })));
  const selected = windows.find(w => w.key === selection) ?? windows[0];
  const sample = selected?.cohort.sample_id; const segment = selected?.id;
  useEffect(() => { if (!sample || !segment) return; let active = true; api.experimentResults(experiment.id, { sample_id: sample, segment_id: segment, latest_references: String(latest) }).then(value => { if (active) { setRows(value.rows); setError(""); } }).catch(failure => { if (active) setError(labError(failure, t)); }); return () => { active = false; stop(); }; }, [experiment.id, experiment.status, sample, segment, latest, t, stop]);
  if (!selected) return null;
  const reference = rows.find(r => r.reference_text)?.reference_text;
  return <section className={styles.panel}><h2>{t("speakingResearch.compare")}</h2>
    <label className={styles.form}>{t("speakingResearch.response")}<select className="field" value={selected.key} onChange={e => setSelection(e.target.value)}>{windows.map(w => <option key={w.key} value={w.key}>{w.cohort.code} · r{w.cohort.review_revision} · Part {w.part_number} · {w.start_ms / 1000}–{w.end_ms / 1000} s</option>)}</select></label>
    <AudioReviewPlayer embedded selectedWindow={{ start_ms: selected.start_ms, end_ms: selected.end_ms }} key={selected.cohort.sample_id} sampleId={selected.cohort.sample_id} durationMs={Math.max(...selected.cohort.windows.map(w => w.end_ms))} playback={playback} />
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    <article><div className={styles.sectionHeading}><h3>{t("speakingResearch.text")}</h3>{reference && <label className={styles.check}><input type="checkbox" checked={showDiff} onChange={e => setShowDiff(e.target.checked)} />{t("speakingResearch.showDiff")}</label>}</div><p className={styles.transcript}>{reference ?? t("speakingResearch.missingTruth")}</p></article>
    <div className={styles.grid}>{rows.map(row => <article className={styles.transcriptBlock} key={row.provider}><div className={styles.providerTitle}><h3>{row.provider}</h3><span>{row.status}</span></div>{!showDiff || !row.reference_text ? <p className={styles.transcript}>{row.text ?? "—"}</p> : <><p className={styles.transcript} aria-label={t("speakingResearch.compare")}>{row.diff.map((v, index) => <span key={index} className={v.kind === "equal" ? undefined : v.kind === "deletion" ? styles.deletion : v.kind === "insertion" ? styles.insertion : styles.substitution} title={`${v.kind}: ${v.reference ?? "∅"} → ${v.hypothesis ?? "∅"}`}>{v.kind === "equal" ? v.hypothesis : `${v.kind === "deletion" ? "−" : v.kind === "insertion" ? "+" : "↔"}${v.kind === "substitution" ? `${v.reference} → ${v.hypothesis}` : v.hypothesis ?? v.reference}`} </span>)}</p><details><summary>{t("speakingResearch.rawTranscript")}</summary><p className={styles.transcript}>{row.text ?? "—"}</p></details></>}<p className={styles.caption}>WER {row.metrics.wer?.toFixed(3) ?? "—"} · CER {row.metrics.cer?.toFixed(3) ?? "—"} · RTF {row.real_time_factor?.toFixed(3) ?? "—"}</p>
      <details><summary>{t("speakingResearch.coverage")}</summary><pre className={styles.code}>{JSON.stringify({ coverage: row.coverage, preservation: row.metrics.preservation }, null, 2)}</pre></details>
      <details><summary>{t("speakingResearch.timings")}</summary><ol>{row.words.map((word, index) => <li key={index}>{word.text} · {word.start_ms == null || word.end_ms == null ? "—" : `${((selected.start_ms + word.start_ms) / 1000).toFixed(2)}–${((selected.start_ms + word.end_ms) / 1000).toFixed(2)} s`} · confidence {word.recognition_confidence ?? "—"}</li>)}</ol></details>
    </article>)}</div>
  </section>;
}
