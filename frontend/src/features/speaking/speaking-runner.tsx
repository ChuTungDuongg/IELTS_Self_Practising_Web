"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { ExamPayload } from "@/lib/api/exam";
import { ApiError } from "@/lib/api/client";
import { closeSpeakingSegment, getSpeakingManifest, openSpeakingSegment, uploadSpeakingChunk, interruptSpeaking, resumeSpeaking, type SpeakingManifest, beginSpeaking, finishSpeaking, getSpeakingState, heartbeatSpeaking, retrySpeaking, saveSpeakingNotes, type SpeakingState } from "@/lib/api/speaking";
import { SpeakingPreflight } from "./speaking-preflight";
import type { SpeakingRecorder } from "./speaking-recorder";
import { SpeakingChunkTransport } from "./speaking-transport";
import { SpeakingAudioPlayer } from "./speaking-review";

export function SpeakingRunner({ initial }: { initial: ExamPayload }) {
  const { t } = useTranslation();
  const id = initial.attempt.attempt_id;
  const [state, setState] = useState<SpeakingState | null>(null);
  const current = useRef<SpeakingState | null>(null);
  const recorder = useRef<SpeakingRecorder | null>(null);
  const transport = useRef<SpeakingChunkTransport | null>(null);
  const [ready, setReady] = useState(false);
  const [preflightGeneration, setPreflightGeneration] = useState(0);
  const [level, setLevel] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [physicalReady, setPhysicalReady] = useState(false);
  const [captureRunning, setCaptureRunning] = useState(false);
  const busy = useRef(false);
  const starting = useRef(false);
  const pendingSegment = useRef<{ promptId: string; take: number; index: number } | null>(null);
  const listening = useRef(false);
  const mounted = useRef(true);
  const [error, setError] = useState(false);
  const [confirmRetry, setConfirmRetry] = useState(false);
  const [manifest, setManifest] = useState<SpeakingManifest | null>(null);
  const [restored, setRestored] = useState(false);
  const [notes, setNotes] = useState("");
  const notesDraft = useRef("");
  const notesDirty = useRef(false);
  const [clock, setClock] = useState(() => Date.now());
  const [received, setReceived] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const accept = useCallback((next: SpeakingState) => {
    if (!mounted.current) return;
    if (current.current?.current_prompt?.id !== next.current_prompt?.id) notesDirty.current = false;
    current.current = next;
    const now = Date.now(); setReceived(now); setClock(now); setState(next);
    if (!notesDirty.current) { notesDraft.current = next.scratch_notes; setNotes(next.scratch_notes); }
  }, []);
  const restore = useCallback(async (recover = true) => {
    setError(false);
    try {
      let next = await getSpeakingState(id);
      if (recover && next.current_prompt && next.take_number && ["PREPARING", "STARTING", "RECORDING", "INTERRUPTED", "RECOVERY_GRACE"].includes(next.phase)) {
        try { next = await interruptSpeaking(id, next.current_prompt.id, next.take_number, next.interruption_generation); }
        catch (caught) {
          if (!(caught instanceof ApiError) || caught.code !== "SPEAKING_RECOVERY_NOT_AVAILABLE") throw caught;
          next = await getSpeakingState(id);
          if (!["FINALIZING", "COMPLETED"].includes(next.phase)) throw caught;
        }
        if (mounted.current) setRestored(true);
      }
      accept(next);
      if (next.response_id && ["INTERRUPTED", "RECOVERY_GRACE"].includes(next.phase)) {
        const accepted = await getSpeakingManifest(id, next.response_id);
        if (mounted.current) setManifest(accepted);
      }
    } catch { if (mounted.current) setError(true); }
  }, [id, accept]);
  useEffect(() => {
    mounted.current = true;
    void Promise.resolve().then(() => { if (mounted.current) return restore(); });
    return () => { mounted.current = false; recorder.current?.close(); };
  }, [restore]);
  useEffect(() => {
    if (!window.matchMedia) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches); update();
    preference.addEventListener?.("change", update); return () => preference.removeEventListener?.("change", update);
  }, []);
  useEffect(() => { if (ready) document.getElementById("speaking-question")?.focus(); }, [state?.current_prompt?.id, state?.take_number, ready]);
  useEffect(() => {
    if (!ready) return;
    let running = false;
    const tick = window.setInterval(() => {
      setClock(Date.now()); const snapshot = current.current;
      if (running || busy.current || !snapshot?.current_prompt || !snapshot.take_number) return;
      running = true;
      void heartbeatSpeaking(id, snapshot.current_prompt.id, snapshot.take_number).then((next) => {
        if (!busy.current && current.current?.current_prompt?.id === snapshot.current_prompt?.id && current.current?.take_number === snapshot.take_number) accept(next);
      }).catch(() => { if (mounted.current) setError(true); }).finally(() => { running = false; });
    }, 1000);
    return () => clearInterval(tick);
  }, [ready, id, accept]);
  const seal = useCallback(async () => {
    await recorder.current?.stop();
    if (mounted.current) setCaptureRunning(false);
    if (transport.current) await transport.current.close();
    const snapshot = current.current;
    if (snapshot?.response_id && !transport.current) {
      const accepted = await getSpeakingManifest(id, snapshot.response_id);
      for (const segment of accepted.segments) if (segment.chunk_count === null) await closeSpeakingSegment(id, segment.id, segment.chunks.length);
    }
  }, [id]);
  const finish = useCallback(async (reason: "USER_DONE" | "TIMEOUT") => {
    const snapshot = current.current;
    if (busy.current || !snapshot?.current_prompt || !snapshot.take_number) return;
    busy.current = true; setSaving(true); setError(false);
    try {
      await seal();
      const next = await finishSpeaking(id, snapshot.current_prompt.id, snapshot.take_number, reason);
      if (next.phase === "COMPLETED") recorder.current?.close();
      transport.current = null; listening.current = false; setPhysicalReady(false); setManifest(null); setRestored(false); setSaved(true); busy.current = false; setSaving(false); accept(next);
    } catch { if (mounted.current) setError(true); }
    finally { busy.current = false; if (mounted.current) setSaving(false); }
  }, [id, accept, seal]);
  const startPhysicalSegment = useCallback(async (snapshot: SpeakingState) => {
    const mic = recorder.current;
    if (!mic || starting.current || transport.current || listening.current || !snapshot.current_prompt || !snapshot.take_number) return;
    starting.current = true; setError(false);
    if (pendingSegment.current?.promptId !== snapshot.current_prompt.id || pendingSegment.current?.take !== snapshot.take_number) pendingSegment.current = { promptId: snapshot.current_prompt.id, take: snapshot.take_number, index: snapshot.next_segment_index };
    try {
      const segment = await openSpeakingSegment(id, snapshot.current_prompt.id, snapshot.take_number, pendingSegment.current.index, mic.mimeType);
      if (!mounted.current || busy.current || current.current?.phase !== "RECORDING" || current.current?.current_prompt?.id !== snapshot.current_prompt.id || current.current?.take_number !== snapshot.take_number) return;
      const queue = new SpeakingChunkTransport((sequence, blob) => uploadSpeakingChunk(id, segment.id, sequence, blob), (count) => closeSpeakingSegment(id, segment.id, count), () => { if (mounted.current && transport.current === queue) { setError(true); setCaptureRunning(false); void mic.stop(); } });
      mic.onChunk = (blob) => queue.enqueue(blob); mic.start(); transport.current = queue; pendingSegment.current = null; setPhysicalReady(true); setCaptureRunning(true);
    } catch { if (mounted.current) setError(true); }
    finally { starting.current = false; }
  }, [id]);
  useEffect(() => {
    if (!state || busy.current) return;
    if (state.phase === "FINALIZING") { void Promise.resolve().then(() => finish("TIMEOUT")); return; }
    if (!ready) return;
    if (state.phase === "QUESTION_ENTER" && state.current_prompt) {
      busy.current = true;
      void beginSpeaking(id, state.current_prompt.id).then((next) => { busy.current = false; accept(next); }).catch(() => setError(true)).finally(() => { busy.current = false; });
    } else if (state.phase === "RECORDING") void Promise.resolve().then(() => startPhysicalSegment(state));
  }, [state, ready, id, accept, finish, startPhysicalSegment]);
  useEffect(() => {
    if (!notesDirty.current || !state?.current_prompt || state.current_prompt.prompt_type !== "LONG_TURN") return;
    const promptId = state.current_prompt.id;
    const timer = setTimeout(() => {
      const value = notesDraft.current;
      void saveSpeakingNotes(id, promptId, value).then(() => { if (notesDraft.current === value) notesDirty.current = false; }).catch(() => { if (mounted.current) setError(true); });
    }, 500);
    return () => clearTimeout(timer);
  }, [notes, id, state?.current_prompt]);
  async function onReady(next: SpeakingRecorder) {
    recorder.current = next; next.onLevel = setLevel; next.onError = () => { if (mounted.current) { setError(true); setCaptureRunning(false); } void next.stop(); };
    try {
      const snapshot = current.current;
      if (snapshot?.current_prompt && snapshot.take_number && ["INTERRUPTED", "RECOVERY_GRACE"].includes(snapshot.phase)) accept(await resumeSpeaking(id, snapshot.current_prompt.id, snapshot.take_number, snapshot.interruption_generation));
      setReady(true);
    } catch {
      next.close(); recorder.current = null; setPreflightGeneration((value) => value + 1);
      try { accept(await getSpeakingState(id)); } catch { /* Keep the last confirmed state for a later retry. */ }
      if (mounted.current) setError(true);
    }
  }
  async function retry() {
    const snapshot = current.current; if (busy.current || !snapshot?.current_prompt || !snapshot.take_number) return;
    busy.current = true; setConfirmRetry(false); setSaving(true); setError(false);
    try { await recorder.current?.stop(); setCaptureRunning(false); const next = await retrySpeaking(id, snapshot.current_prompt.id, snapshot.take_number); transport.current?.dispose(); transport.current = null; listening.current = false; setPhysicalReady(false); setManifest(null); setRestored(false); busy.current = false; setSaving(false); accept(next); }
    catch { setError(true); } finally { busy.current = false; setSaving(false); }
  }
  async function listen() {
    if (busy.current) return;
    busy.current = true; listening.current = true; setSaving(true);
    try { await seal(); if (current.current?.response_id) setManifest(await getSpeakingManifest(id, current.current.response_id)); }
    catch { setError(true); } finally { busy.current = false; setSaving(false); }
  }
  const prompt = state?.current_prompt;
  const milliseconds = state ? Math.max(0, state.remaining_ms - (state.phase === "PREPARING" || state.phase === "RECORDING" || state.phase === "STARTING" ? Math.max(0, clock - received) : 0)) : 0;
  useEffect(() => {
    if (ready && state?.phase === "RECORDING" && milliseconds === 0) void Promise.resolve().then(() => finish("TIMEOUT"));
  }, [ready, state?.phase, milliseconds, finish]);
  const seconds = Math.ceil(milliseconds / 1000); const time = `${Math.floor(seconds / 60).toString().padStart(2,"0")}:${(seconds % 60).toString().padStart(2,"0")}`;
  const grace = state?.recovery_grace_deadline_at ? Math.max(0, Math.ceil((new Date(state.recovery_grace_deadline_at).getTime() - new Date(state.server_time).getTime() - Math.max(0, clock - received)) / 1000)) : 0;
  return <main className="exam-runner speaking-runner" data-reduced-motion={reducedMotion}>
    <header className="exam-header"><h1>{initial.test_title}</h1><ThemeToggle /></header>
    {error ? <div className="notice notice-error" role="alert">{t("speakingRuntime.saveError")}<button className="btn btn-secondary" disabled={saving} onClick={() => void (state?.phase === "FINALIZING" ? finish("TIMEOUT") : state?.phase === "RECORDING" && ready ? physicalReady ? finish("USER_DONE") : startPhysicalSegment(state) : restore(!ready))}>{t("speakingRuntime.saveAgain")}</button></div> : null}
    {!state ? <p role="status">{t("speakingRuntime.loading")}</p> : state.phase === "COMPLETED" ? <div className="speaking-card"><h2>{t("speakingRuntime.completed")}</h2><a className="btn btn-primary" href={`/review/${id}`}>{t("speakingRuntime.review")}</a></div> : <>
      {restored ? <p role="status">{t("speakingRuntime.restored")}{manifest?.segments.some((segment) => segment.chunks.length) ? ` · ${t("speakingRuntime.recoveredAudio")}` : ""}</p> : null}
      {!ready && state.phase !== "FINALIZING" ? <SpeakingPreflight key={preflightGeneration} onReady={onReady} /> : null}
      {prompt ? <section className="speaking-card speaking-question" key={prompt.id} aria-labelledby="speaking-question">
        <p>{t("speaking.part", { number: prompt.part_number })}</p><h2 id="speaking-question" tabIndex={-1}>{prompt.prompt_text}</h2>
        {prompt.instructions ? <p>{prompt.instructions}</p> : null}
        {prompt.config_json.cue_points?.length ? <ul>{prompt.config_json.cue_points.map((point, index) => <li key={index}>{point}</li>)}</ul> : null}
        {ready ? <><div className={`speaking-status ${state.phase === "RECORDING" && captureRunning ? "speaking-is-recording" : ""}`} aria-live="polite"><span>{saving ? t("speakingRuntime.saving") : state.phase === "RECOVERY_GRACE" ? t("speakingRuntime.grace", { count: grace }) : t(state.phase === "PREPARING" ? "speakingRuntime.preparing" : state.phase === "STARTING" ? "speakingRuntime.starting" : captureRunning ? "speakingRuntime.recording" : "speakingRuntime.stopped")}</span><span role="timer" aria-live="off" className={seconds < 10 ? "exam-timer-warning" : ""}>{time}</span></div>
          <progress max={state.phase === "PREPARING" ? prompt.preparation_seconds * 1000 : state.phase === "STARTING" ? 3000 : prompt.response_seconds * 1000} value={milliseconds} aria-label={t("speakingRuntime.remaining")} />
          <meter aria-label={t("speakingRuntime.level")} min={0} max={1} value={level} />
          {prompt.prompt_type === "LONG_TURN" ? <label className="field-label">{t("speakingRuntime.notes")}<textarea aria-label={t("speakingRuntime.notes")} value={notes} maxLength={20000} disabled={saving} onChange={(event) => { notesDirty.current = true; notesDraft.current = event.target.value; setNotes(event.target.value); }} /><small>{t("speakingRuntime.notesHint")}</small></label> : null}
          <div className="speaking-controls">
            {state.can_replay ? <button className="btn btn-secondary" disabled={saving || !physicalReady} onClick={() => void listen()}>{t("speakingRuntime.listen")}</button> : null}
            {state.can_retry ? <button className="btn btn-secondary" id="speaking-retry" disabled={saving || !physicalReady} onClick={() => setConfirmRetry(true)}>{t("speakingRuntime.retry")}</button> : null}
            <button className="btn btn-primary" disabled={saving || !["RECORDING","FINALIZING"].includes(state.phase) || (state.phase === "RECORDING" && !physicalReady)} onClick={() => void finish(state.phase === "FINALIZING" ? "TIMEOUT" : "USER_DONE")}>{t("speakingRuntime.done")}</button>
          </div>{manifest && state.can_replay ? <SpeakingAudioPlayer segments={manifest.segments} /> : null}{saved ? <p role="status">{t("speakingRuntime.saved")}</p> : null}
        </> : null}
      </section> : null}
    </>}
    {confirmRetry ? <div role="dialog" aria-modal="true" aria-label={t("speakingRuntime.retry")} className="speaking-card" onKeyDown={(event) => {
      if (event.key === "Escape") { setConfirmRetry(false); document.getElementById("speaking-retry")?.focus(); }
      if (event.key === "Tab") { const buttons = event.currentTarget.querySelectorAll("button"); event.preventDefault(); (event.target === buttons[0] ? buttons[1] : buttons[0]).focus(); }
    }}><p>{t("speakingRuntime.retryHint")}</p><button className="btn btn-primary" autoFocus onClick={() => void retry()}>{t("speakingRuntime.confirmRetry")}</button><button className="btn btn-secondary" onClick={() => { setConfirmRetry(false); document.getElementById("speaking-retry")?.focus(); }}>{t("common.cancel")}</button></div> : null}
  </main>;
}
