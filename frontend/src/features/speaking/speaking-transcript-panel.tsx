"use client";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { activeTranscript, createTranscriptRun, getTranscriptRun, latestTranscriptRun, watchTranscriptRun, type TranscriptRun } from "@/lib/api/speaking-transcript";

const TranscriptContext = createContext<TranscriptRun | null>(null);
export function SpeakingTranscriptSession({ attemptId, canGenerate = true, refreshKey = 0, children }: { attemptId: string; canGenerate?: boolean; refreshKey?: number; children: ReactNode }) {
  const { t } = useTranslation(); const [run, setRun] = useState<TranscriptRun | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(false);
  const alive = useRef(true); const pending = useRef(false); const cursor = useRef(0);
  const [loading, setLoading] = useState(true);
  const runId = run?.run_id; const isActive = activeTranscript(run);
  useEffect(() => {
    let cancelled = false; alive.current = true;
    void latestTranscriptRun(attemptId).then((next) => { if (!cancelled && alive.current) { cursor.current = next?.last_sequence ?? 0; setRun(next); setError(false); } }).catch(() => { if (!cancelled && alive.current) setError(true); }).finally(() => { if (!cancelled && alive.current) setLoading(false); });
    return () => { cancelled = true; alive.current = false; };
  }, [attemptId, refreshKey]);
  useEffect(() => {
    if (!runId || !isActive) return;
    return watchTranscriptRun(attemptId, runId, { event: () => undefined, snapshot: (next) => { if (alive.current) { cursor.current = next.last_sequence; setRun(next); setError(false); } }, error: () => { if (alive.current) setError(true); } }, cursor.current);
  }, [attemptId, runId, isActive]);
  async function generate() {
    if (pending.current || !canGenerate || loading) return; pending.current = true; setBusy(true); setError(false);
    try { const next = await createTranscriptRun(attemptId); const snapshot = await getTranscriptRun(attemptId, next.run_id); if (alive.current) setRun(snapshot); }
    catch { if (alive.current) setError(true); } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <TranscriptContext.Provider value={run}><div className="speaking-controls">
    {canGenerate ? <button className="btn btn-secondary" disabled={loading || busy || activeTranscript(run)} onClick={() => void generate()}>{t(run?.status === "FAILED" || run?.status === "PARTIAL" ? "speakingTranscript.retry" : "speakingTranscript.generate")}</button> : null}
    {busy || activeTranscript(run) ? <p role="status">{t("speakingTranscript.processing")}</p> : null}
    {error ? <p role="alert" className="notice notice-error">{t("speakingTranscript.error")}</p> : null}
  </div>{children}</TranscriptContext.Provider>;
}
export function SpeakingTranscriptResponse({ responseId }: { responseId: string }) {
  const { t } = useTranslation(); const run = useContext(TranscriptContext); const response = run?.responses.find((r) => r.response_id === responseId);
  const status = response?.status ?? "WAITING";
  return <section className="speaking-transcript" aria-label={t("speakingTranscript.title")}><h3>{t("speakingTranscript.title")}</h3>
    <p role="status">{t(status === "READY" ? "speakingTranscript.ready" : status === "FAILED" ? "speakingTranscript.failed" : status === "PROCESSING" ? "speakingTranscript.processing" : "speakingTranscript.waiting")}</p>
    {status === "READY" ? <p className="speaking-transcript-text">{response?.verbatim}</p> : null}
  </section>;
}
