"use client";
import { useEffect, useRef, useState } from "react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { fetchSpeakingAudio, type SpeakingReviewData, type SpeakingManifest } from "@/lib/api/speaking";

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
export function SpeakingReview({ data }: { data: SpeakingReviewData }) {
  const { t } = useTranslation();
  return <main className="speaking-runner"><header className="exam-header"><h1>{data.test_title}</h1><ThemeToggle /></header>
    {data.parts.map((part) => <section key={part.part_number} aria-label={t("speaking.part", { number: part.part_number })}><h2>{t("speaking.part", { number: part.part_number })}</h2>
      {part.responses.map(({ prompt, response, segments }) => <details key={response.id} className="speaking-card speaking-question"><summary>{prompt.prompt_text}</summary>
        {prompt.config_json.cue_points?.length ? <ul>{prompt.config_json.cue_points.map((point, index) => <li key={index}>{point}</li>)}</ul> : null}
        <p>{Math.round(response.duration_ms / 1000)} s</p><p>{t(response.completion_reason === "TIMEOUT" ? "speakingRuntime.timedOut" : response.completion_reason === "INTERRUPTED" ? "speakingRuntime.interrupted" : "speakingRuntime.saved")}</p>
        <SpeakingAudioPlayer segments={segments} /></details>)}
    </section>)}
  </main>;
}
