"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ApiError } from "@/lib/api/client";
import { activeSpeakingAI, cancelSpeakingAIRun, createSpeakingAIRun, getSpeakingAIRun, latestSpeakingAIRun, watchSpeakingAIRun, type SpeakingAICriterion, type SpeakingAIRun } from "@/lib/api/speaking-ai";
import { SpeakingAIProgress } from "./speaking-ai-progress";

const criteria: SpeakingAICriterion[] = ["fc", "lr", "gra", "pr"];
export function SpeakingAIAssessment({ attemptId, canGrade = true, onTranscriptAvailable, onCopy, canCopy = false, initialRun }: { attemptId: string; canGrade?: boolean; onTranscriptAvailable?: () => void; canCopy?: boolean; onCopy?: (run: SpeakingAIRun) => void; initialRun?: SpeakingAIRun | null }) {
  return <AssessmentSession key={`${attemptId}:${canGrade}`} attemptId={attemptId} canGrade={canGrade} onTranscriptAvailable={onTranscriptAvailable} canCopy={canCopy} onCopy={onCopy} initialRun={initialRun} />;
}
function AssessmentSession({ attemptId, canGrade, onTranscriptAvailable, onCopy, canCopy, initialRun }: { attemptId: string; canGrade: boolean; onTranscriptAvailable?: () => void; canCopy: boolean; onCopy?: (run: SpeakingAIRun) => void; initialRun?: SpeakingAIRun | null }) {
  const { t } = useTranslation(); const [run, setRun] = useState<SpeakingAIRun | null>(initialRun ?? null);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState<"generic" | "notConfigured" | null>(null); const [reducedMotion, setReducedMotion] = useState(false);
  const alive = useRef(true); const pending = useRef(false); const current = useRef<SpeakingAIRun | null>(null);
  const announcedTranscripts = useRef(new Set<string>());
  const runId = run?.run_id; const active = activeSpeakingAI(run);
  function accept(next: SpeakingAIRun, acknowledgedRetry = false) {
    if (!alive.current) return;
    const previous = current.current;
    if (previous?.run_id === next.run_id) {
      if (next.last_sequence < previous.last_sequence) return;
      // Only the response to an explicit Grade request may reopen a logical run.
      if (!activeSpeakingAI(previous) && activeSpeakingAI(next) && (!acknowledgedRetry || next.last_sequence <= previous.last_sequence)) return;
    }
    current.current = next; setRun(next); setError(null);
  }
  useEffect(() => {
    alive.current = true; void (initialRun ? Promise.resolve(initialRun) : latestSpeakingAIRun(attemptId)).then((next) => { if (next) accept(next); }).catch(() => { if (alive.current) setError("generic"); }).finally(() => { if (alive.current) setLoading(false); });
    return () => { alive.current = false; };
  }, [attemptId, initialRun]);
  useEffect(() => {
    if (!runId || !active) return;
    return watchSpeakingAIRun(attemptId, runId, { event: () => undefined, snapshot: accept, error: () => { if (alive.current) setError("generic"); } }, current.current?.last_sequence ?? 0);
  }, [attemptId, runId, active]);
  useEffect(() => {
    if (!run || !onTranscriptAvailable || announcedTranscripts.current.has(run.run_id)) return;
    const transcriptReady = ["ANALYSING_AUDIO", "BUILDING_EVIDENCE", "SCORING", "GENERATING_FEEDBACK", "COMPLETED"].includes(run.stage);
    if (!transcriptReady) return;
    announcedTranscripts.current.add(run.run_id); onTranscriptAvailable();
  }, [run, onTranscriptAvailable]);
  useEffect(() => {
    if (!window.matchMedia) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(preference.matches); sync(); preference.addEventListener("change", sync);
    return () => preference.removeEventListener("change", sync);
  }, []);
  async function grade() {
    if (pending.current || loading || !canGrade || activeSpeakingAI(current.current)) return;
    pending.current = true; setBusy(true); setError(null);
    try {
      const next = await createSpeakingAIRun(attemptId); const snapshot = await getSpeakingAIRun(attemptId, next.run_id);
      accept(snapshot, !next.cache_hit && snapshot.run_id === next.run_id);
    }
    catch (caught) { if (alive.current) setError(caught instanceof ApiError && caught.code === "SPEAKING_AI_NOT_CONFIGURED" ? "notConfigured" : "generic"); } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  async function stop() {
    if (pending.current || !canGrade || !current.current || !activeSpeakingAI(current.current)) return;
    pending.current = true; setBusy(true); setError(null);
    try { accept(await cancelSpeakingAIRun(attemptId, current.current.run_id)); }
    catch { if (alive.current) setError("generic"); } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <section className="speaking-card speaking-ai-assessment" aria-label={t("speakingAI.title")} data-reduced-motion={reducedMotion}>
    <div className="speaking-controls"><h2>{t("speakingAI.title")}</h2>{canGrade ? <div className="speaking-ai-actions">
      <button className="btn btn-primary" disabled={loading || busy || active} onClick={() => void grade()}>{t("speakingAI.grade")}</button>
      {active ? <button className="btn btn-secondary" disabled={busy} onClick={() => void stop()}>{t("speakingAI.stop")}</button> : null}
    </div> : null}</div>
    <p className="speaking-ai-advisory">{t("speakingAI.advisory")}</p>
    {error ? <p role="alert" className="notice notice-error">{t(error === "notConfigured" ? "speakingAI.notConfigured" : "speakingAI.error")}</p> : null}
    {run ? <><SpeakingAIProgress run={run} />
      {canCopy && onCopy && run.attempt_id === attemptId && run.status === "COMPLETED" && criteria.every(key => run.criteria[key].status === "COMPLETED" && run.criteria[key].score !== null) ? <button type="button" className="btn btn-secondary" onClick={() => onCopy(run)}>{t("grading.copy")}</button> : null}
      {run.status === "FAILED" ? <p className="notice notice-error">{t(run.error_code === "SPEAKING_AUDIO_UNASSESSABLE" ? "speakingAI.audioUnavailable" : "speakingAI.failed")}</p> : null}
      <div className="speaking-ai-overall"><h3>{t("speakingAI.overall")}</h3><p className="speaking-ai-score">{run.overall_band === null ? t("speakingAI.overallWaiting") : run.overall_band.toFixed(1)}</p>
        {run.raw_mean !== null ? <p>{t("speakingAI.rawMean", { value: run.raw_mean })}</p> : null}</div>
      <div className="speaking-ai-criteria">{criteria.map((key) => {
        const result = run.criteria[key]; const unavailable = result.status === "UNAVAILABLE" || (key === "pr" && result.error_code === "SPEAKING_AUDIO_UNASSESSABLE");
        const responseCount = result.evidence_summary.response_count;
        return <section className="speaking-ai-criterion" key={key} aria-label={t(`speakingAI.criterion.${key}`)}><h3>{t(`speakingAI.criterion.${key}`)}</h3>
          <p className="speaking-ai-score">{result.score === null ? "—" : result.score.toFixed(1)}</p>
          {unavailable ? <p>{t("speakingAI.audioUnavailable")}</p> : result.status === "FAILED" ? <p>{t("speakingAI.criterionFailed")}</p> : result.score === null ? <p>{t(result.status === "SCORING" ? "speakingAI.scoring" : "speakingAI.waiting")}</p> : null}
          {result.score !== null && result.feedback_status === "FALLBACK" ? <p>{t("speakingAI.feedbackFallback")}</p> : result.feedback_status === "READY" && result.feedback ? <p>{result.feedback}</p> : result.score !== null && result.feedback_status === "PENDING" ? <p>{t("speakingAI.feedbackPending")}</p> : null}
          {result.strengths.length ? <><h4>{t("speakingAI.strengths")}</h4><ul>{result.strengths.map((item, index) => <li key={index}>{item}</li>)}</ul></> : null}
          {result.improvements.length ? <><h4>{t("speakingAI.improvements")}</h4><ul>{result.improvements.map((item, index) => <li key={index}>{item}</li>)}</ul></> : null}
          {typeof responseCount === "number" && Number.isInteger(responseCount) && responseCount >= 0 && responseCount <= 1000 ? <small>{t("speakingAI.scope", { count: responseCount })}</small> : null}
        </section>;
      })}</div>
      {run.summary.responses.length ? <section className="speaking-ai-evidence" aria-label={t("speakingAI.evidence")}><h3>{t("speakingAI.evidence")}</h3><p>{t("speakingAI.evidenceHint")}</p>
        {run.summary.responses.map((response, index) => <div key={response.response_id}><h4>{t("speakingAI.response", { number: index + 1, part: response.part_number })}</h4><ul>
          {response.words_per_minute !== null ? <li>{t("speakingAI.wordsPerMinute", { value: Math.round(response.words_per_minute) })}</li> : null}
          {response.part_number === 2 && response.part2_sustained_seconds !== null ? <li>{t("speakingAI.sustained", { value: Math.round(response.part2_sustained_seconds) })}</li> : null}
          <li>{t(`speakingAI.pronunciation.${response.pronunciation_status}`)}</li>
          {response.mean_alignment_confidence !== null ? <li>{t("speakingAI.alignment", { value: Math.round(response.mean_alignment_confidence * 100) })}</li> : null}
          {response.pitch_range_hz !== null ? <li>{t("speakingAI.pitch", { value: Math.round(response.pitch_range_hz) })}</li> : null}
          {response.limitations.length ? <li>{t("speakingAI.limitations")}</li> : null}
        </ul></div>)}</section> : null}
    </> : loading ? <p>{t("speakingAI.loading")}</p> : <p>{t("speakingAI.ready")}</p>}
  </section>;
}
