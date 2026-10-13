"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { fetchSpeakingAudio, type SpeakingReviewData, type SpeakingManifest } from "@/lib/api/speaking";
import { SpeakingTranscriptResponse, SpeakingTranscriptSession } from "./speaking-transcript-panel";
import { SpeakingFinalScore } from "./speaking-final-score";
import type { AssignmentGradingScope } from "@/lib/api/grading";
import type { SpeakingAIRun } from "@/lib/api/speaking-ai";
import { SpeakingAIAssessment } from "./speaking-ai-assessment";
import { focusedUnitLabel } from "@/features/exam/focused-attempt";

export function SpeakingAudioPlayer({ segments }: Pick<SpeakingManifest, "segments">) {
  const { t } = useTranslation(); const [urls, setUrls] = useState<string[]>([]); const [error, setError] = useState(false); const [loading, setLoading] = useState(false);
  useEffect(() => () => urls.forEach((url) => URL.revokeObjectURL(url)), [urls]);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function load() {
    setLoading(true); setError(false); const next: string[] = [];
    try { for (const segment of segments) { if (segment.content_url && segment.chunks.length) { const blob = await fetchSpeakingAudio(segment.content_url); if (!mounted.current) { next.forEach((url) => URL.revokeObjectURL(url)); return; } next.push(URL.createObjectURL(blob)); } } setUrls(next); }
    catch { next.forEach((url) => URL.revokeObjectURL(url)); setError(true); } finally { setLoading(false); }
  }
  return <div>{!urls.length ? <button className="btn btn-secondary" disabled={loading || !segments.some((s) => s.chunks.length && s.content_url)} onClick={() => void load()}>{t(loading ? "speakingRuntime.loadingAudio" : "speakingRuntime.loadAudio")}</button> : urls.map((url, index) => <audio key={url} controls preload="metadata" src={url} aria-label={t("speakingRuntime.segment", { number: index + 1 })} />)}{error ? <p role="alert" className="notice notice-error">{t("speakingRuntime.audioError")}</p> : null}</div>;
}
export function SpeakingReview({ data, assignmentScope, initialAIRun }: { data: SpeakingReviewData; assignmentScope?: AssignmentGradingScope; initialAIRun?: SpeakingAIRun | null }) {
  const { t } = useTranslation();
  const [copiedRun, setCopiedRun] = useState<SpeakingAIRun | null>(null);
  const [transcriptRefreshKey, setTranscriptRefreshKey] = useState(0);
  const refreshTranscript = useCallback(() => setTranscriptRefreshKey((key) => key + 1), []);
  return <main className="speaking-runner"><header className="exam-header"><h1>{data.test_title}</h1></header>
    {data.focused_unit ? <p>{focusedUnitLabel({ scope: "FOCUSED_UNIT", focused_unit: data.focused_unit }, t)}{data.practice_flow ? ` · ${t(data.practice_flow === "FREE" ? "speakingPractice.free" : "speakingPractice.guided")}` : ""}</p> : null}
    <SpeakingFinalScore key={data.attempt_id} data={data} assignmentScope={assignmentScope} copiedRun={copiedRun} />
    <SpeakingTranscriptSession attemptId={data.attempt_id} canGenerate={data.can_generate_transcript} refreshKey={transcriptRefreshKey}>
    <SpeakingAIAssessment attemptId={data.attempt_id} canGrade={data.can_generate_transcript} onTranscriptAvailable={refreshTranscript} initialRun={initialAIRun} partNumber={data.focused_unit?.kind === "SPEAKING_PART" ? data.focused_unit.order_index + 1 : undefined} canCopy={data.grading?.can_edit_final === true && data.grading?.can_copy_ai_to_final === true} onCopy={run => setCopiedRun({ ...run })} />
    {data.parts.map((part) => <section key={part.part_number} aria-label={t("speaking.part", { number: part.part_number })}><h2>{t("speaking.part", { number: part.part_number })}</h2>
      {[...part.responses.map(item => ({ prompt: item.prompt, item })), ...(part.unanswered_prompts ?? []).map(prompt => ({ prompt, item: null }))].sort((a, b) => a.prompt.order_index - b.prompt.order_index).map(({ prompt, item }) => item ? <details key={item.response.id} className="speaking-card speaking-question"><summary>{prompt.prompt_text}</summary>
        {prompt.config_json.cue_points?.length ? <ul>{prompt.config_json.cue_points.map((point, index) => <li key={index}>{point}</li>)}</ul> : null}
        <p>{Math.round(item.response.duration_ms / 1000)} s</p><p>{t(item.response.completion_reason === "TIMEOUT" ? "speakingRuntime.timedOut" : item.response.completion_reason === "INTERRUPTED" ? "speakingRuntime.interrupted" : "speakingRuntime.saved")}</p>
        <SpeakingAudioPlayer segments={item.segments} /><SpeakingTranscriptResponse responseId={item.response.id} /></details> : <article key={prompt.id} className="speaking-card speaking-question"><h3>{prompt.prompt_text}</h3><p>{t("speakingPractice.unanswered")}</p></article>)}
    </section>)}
    </SpeakingTranscriptSession>
  </main>;
}
