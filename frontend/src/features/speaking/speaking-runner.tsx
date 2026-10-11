"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { ExamPayload } from "@/lib/api/exam";
import { beginSpeaking, finishSpeaking, getSpeakingState, heartbeatSpeaking, retrySpeaking, saveSpeakingNotes, type SpeakingState } from "@/lib/api/speaking";
import { SpeakingPreflight } from "./speaking-preflight";
import type { SpeakingRecorder } from "./speaking-recorder";

export function SpeakingRunner({ initial }: { initial: ExamPayload }) {
  const { t } = useTranslation(); const id = initial.attempt.attempt_id;
  const [state, setState] = useState<SpeakingState | null>(null);
  const current = useRef<SpeakingState | null>(null);
  const recorder = useRef<SpeakingRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [ready, setReady] = useState(false);
  const [level, setLevel] = useState(0);
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const [error, setError] = useState(false);
  const [confirmRetry, setConfirmRetry] = useState(false);
  const [listenUrl, setListenUrl] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [clock, setClock] = useState(() => Date.now());
  const [received, setReceived] = useState(0);
  const accept = useCallback((next: SpeakingState) => { current.current = next; const now = Date.now(); setReceived(now); setClock(now); setState(next); setNotes(next.scratch_notes); }, []);
  useEffect(() => { let active = true; void getSpeakingState(id).then((next) => { if (active) accept(next); }).catch(() => { if (active) setError(true); }); return () => { active = false; recorder.current?.close(); }; }, [id, accept]);
  useEffect(() => { if (!ready) return; let running = false; const tick = window.setInterval(() => {
    setClock(Date.now()); const snapshot = current.current;
    if (running || busy.current || !snapshot?.current_prompt || !snapshot.take_number) return;
    running = true;
    void heartbeatSpeaking(id, snapshot.current_prompt.id, snapshot.take_number).then(accept).catch(() => setError(true)).finally(() => { running = false; });
  }, 1000); return () => clearInterval(tick); }, [ready, id, accept]);
  const finish = useCallback(async (reason: "USER_DONE" | "TIMEOUT") => {
    const snapshot = current.current; if (busy.current || !snapshot?.current_prompt || !snapshot.take_number) return;
    busy.current = true; setSaving(true); setError(false);
    try { await recorder.current?.stop(); const next = await finishSpeaking(id, snapshot.current_prompt.id, snapshot.take_number, reason); accept(next); chunks.current = []; }
    catch { setError(true); } finally { busy.current = false; setSaving(false); }
  }, [id, accept]);
  useEffect(() => { if (!ready || !state || busy.current) return;
    if (state.phase === "QUESTION_ENTER" && state.current_prompt) {
      busy.current = true; void beginSpeaking(id, state.current_prompt.id).then(accept).catch(() => setError(true)).finally(() => { busy.current = false; });
    } else if (state.phase === "RECORDING") recorder.current?.start();
    else if (state.phase === "FINALIZING") void finish("TIMEOUT");
  }, [state, ready, id, accept, finish]);
  useEffect(() => () => { if (listenUrl) URL.revokeObjectURL(listenUrl); }, [listenUrl]);
  async function onReady(next: SpeakingRecorder) {
    recorder.current = next; next.onLevel = setLevel; next.onError = () => setError(true);
    next.onChunk = (chunk) => chunks.current.push(chunk); setReady(true);
  }
  async function retry() {
    const snapshot = current.current; if (busy.current || !snapshot?.current_prompt || !snapshot.take_number) return;
    busy.current = true; setConfirmRetry(false); setSaving(true); setError(false);
    try { await recorder.current?.stop(); accept(await retrySpeaking(id, snapshot.current_prompt.id, snapshot.take_number)); chunks.current = []; setListenUrl(null); }
    catch { setError(true); } finally { busy.current = false; setSaving(false); }
  }
  async function listen() { await recorder.current?.stop(); setListenUrl(URL.createObjectURL(new Blob(chunks.current, { type: recorder.current?.mimeType }))); }
  const prompt = state?.current_prompt;
  const milliseconds = state ? Math.max(0, state.remaining_ms - (state.phase === "PREPARING" || state.phase === "RECORDING" || state.phase === "STARTING" ? Math.max(0, clock - received) : 0)) : 0;
  const seconds = Math.ceil(milliseconds / 1000); const time = `${Math.floor(seconds / 60).toString().padStart(2,"0")}:${(seconds % 60).toString().padStart(2,"0")}`;
  return <main className="exam-runner speaking-runner">
    <header className="exam-header"><h1>{initial.test_title}</h1><ThemeToggle /></header>
    {error ? <div className="notice notice-error" role="alert">{t("speakingRuntime.saveError")}<button className="btn btn-secondary" onClick={() => void (state?.phase === "FINALIZING" ? finish("TIMEOUT") : finish("USER_DONE"))}>{t("speakingRuntime.saveAgain")}</button></div> : null}
    {!state ? <p role="status">{t("speakingRuntime.loading")}</p> : state.phase === "COMPLETED" ? <div className="speaking-card"><h2>{t("speakingRuntime.completed")}</h2><a className="btn btn-primary" href={`/review/${id}`}>{t("speakingRuntime.review")}</a></div> : <>
      {!ready ? <SpeakingPreflight onReady={onReady} /> : null}
      {prompt ? <section className="speaking-card speaking-question" key={prompt.id} aria-labelledby="speaking-question">
        <p>{t("speaking.part", { number: prompt.part_number })}</p><h2 id="speaking-question" tabIndex={-1}>{prompt.prompt_text}</h2>
        {prompt.instructions ? <p>{prompt.instructions}</p> : null}
        {prompt.config_json.cue_points?.length ? <ul>{prompt.config_json.cue_points.map((point, index) => <li key={index}>{point}</li>)}</ul> : null}
        {ready ? <><div className="speaking-status" aria-live="polite"><span>{saving ? t("speakingRuntime.saving") : t(state.phase === "PREPARING" ? "speakingRuntime.preparing" : state.phase === "STARTING" ? "speakingRuntime.starting" : "speakingRuntime.recording")}</span><span role="timer" aria-live="off">{time}</span></div>
          <progress max={state.phase === "PREPARING" ? prompt.preparation_seconds * 1000 : state.phase === "STARTING" ? 3000 : prompt.response_seconds * 1000} value={milliseconds} aria-label={t("speakingRuntime.remaining")} />
          <meter aria-label={t("speakingRuntime.level")} min={0} max={1} value={level} />
          {prompt.prompt_type === "LONG_TURN" ? <label className="field-label">{t("speakingRuntime.notes")}<textarea aria-label={t("speakingRuntime.notes")} value={notes} maxLength={20000} disabled={saving} onChange={(event) => setNotes(event.target.value)} onBlur={() => { if (notes !== state.scratch_notes) void saveSpeakingNotes(id, prompt.id, notes).then(accept).catch(() => setError(true)); }} /><small>{t("speakingRuntime.notesHint")}</small></label> : null}
          <div className="speaking-controls">
            {state.can_replay ? <button className="btn btn-secondary" disabled={saving} onClick={() => void listen()}>{t("speakingRuntime.listen")}</button> : null}
            {state.can_retry ? <button className="btn btn-secondary" disabled={saving} onClick={() => setConfirmRetry(true)}>{t("speakingRuntime.retry")}</button> : null}
            <button className="btn btn-primary" disabled={saving || !["RECORDING","FINALIZING"].includes(state.phase)} onClick={() => void finish(state.phase === "FINALIZING" ? "TIMEOUT" : "USER_DONE")}>{t("speakingRuntime.done")}</button>
          </div>{listenUrl ? <audio controls src={listenUrl} aria-label={t("speakingRuntime.listen")} /> : null}
        </> : null}
      </section> : null}
    </>}
    {confirmRetry ? <div role="dialog" aria-modal="true" aria-label={t("speakingRuntime.retry")} className="speaking-card"><p>{t("speakingRuntime.retryHint")}</p><button className="btn btn-primary" autoFocus onClick={() => void retry()}>{t("speakingRuntime.confirmRetry")}</button><button className="btn btn-secondary" onClick={() => setConfirmRetry(false)}>{t("common.cancel")}</button></div> : null}
  </main>;
}
