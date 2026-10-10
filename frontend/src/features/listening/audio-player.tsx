"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { formatAudioTime, validAudioClip, type AudioClip } from "./audio-time";

const speeds = [0.75, 1, 1.25, 1.5, 2];
export type AudioPolicy = { allowSeeking: boolean; allowSpeed: boolean };

export type ListeningAudioPlayerHandle = { currentPosition: () => number; preview: (clip: AudioClip) => void };

export function ListeningAudioPlayer({ src, clip, policy = { allowSeeking: true, allowSpeed: true }, ref, onDuration }: {
  src: string; clip?: AudioClip; policy?: AudioPolicy; ref?: Ref<ListeningAudioPlayerHandle>; onDuration?: (seconds: number) => void;
}) {
  const { t } = useTranslation();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [preview, setPreview] = useState<AudioClip | undefined>();
  const [previewRequest, setPreviewRequest] = useState(0);
  const previewPending = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [playError, setPlayError] = useState(false);
  const activeClip = clip ?? preview;
  const start = activeClip?.startSeconds ?? 0;
  const end = activeClip?.endSeconds ?? duration;
  const clipError = Boolean(activeClip && (!validAudioClip(activeClip) || (duration > 0 && end > duration)));
  const length = Math.max(0, end - start);
  const unavailable = state === "error" || clipError;

  useImperativeHandle(ref, () => ({
    currentPosition: () => audioRef.current?.currentTime ?? 0,
    preview: (range) => { if (!policy.allowSeeking) return; previewPending.current = true; setPreview(range); setPreviewRequest((value) => value + 1); },
  }), [policy.allowSeeking]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    previewPending.current = false;
    setPreview(undefined);
    setPlaying(false);
    setCurrent(0);
    setDuration(0);
    setPlayError(false);
    setState("loading");
    audio.load();
    return () => audio.pause();
  }, [src]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    setPlaying(false);
    setCurrent(start);
    setPlayError(false);
    if (!clipError && duration > 0) {
      audio.currentTime = start;
      if (previewPending.current) { previewPending.current = false; void audio.play().catch(() => setPlayError(true)); }
    } else if (clipError) previewPending.current = false;
  }, [start, end, duration, clipError, previewRequest]);

  function seek(value: number) {
    const audio = audioRef.current;
    if (!audio || !policy.allowSeeking || unavailable || !duration) return;
    const next = Math.max(start, Math.min(end, value));
    audio.currentTime = next;
    if (activeClip && next === end) { audio.pause(); setPlaying(false); }
    setCurrent(next);
  }
  async function toggle() {
    const audio = audioRef.current;
    if (!audio || unavailable) return;
    if (audio.paused) {
      if (activeClip && (audio.currentTime >= end || audio.currentTime < start)) { audio.currentTime = start; setCurrent(start); }
      setPlayError(false);
      try { await audio.play(); } catch { setPlayError(true); }
    } else audio.pause();
  }

  return <><div className="listening-player" aria-label={t("runner.audioPlayer")}><audio ref={audioRef} src={src} preload="metadata" onLoadedMetadata={(event) => {
      const value = event.currentTarget.duration;
      if (!Number.isFinite(value) || value <= 0) { setState("error"); return; }
      setDuration(value); onDuration?.(value); setState("ready");
    }} onTimeUpdate={(event) => {
      const audio = event.currentTarget;
      if (activeClip && !clipError) {
        if (audio.currentTime >= end) { audio.pause(); audio.currentTime = end; setPlaying(false); }
        else if (audio.currentTime < start) audio.currentTime = start;
      }
      setCurrent(audio.currentTime);
    }} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onWaiting={() => setState("loading")} onCanPlay={() => setState((currentState) => currentState === "error" ? "error" : "ready")} onError={() => setState("error")} />
    <button type="button" className="player-main" disabled={unavailable || (Boolean(activeClip) && !duration)} onClick={() => void toggle()} aria-label={playing ? t("runner.pauseAudio") : t("runner.playAudio")}>{playing ? "❚❚" : "▶"}</button>
    <button type="button" className="player-skip" disabled={!policy.allowSeeking || unavailable} onClick={() => seek(current - 10)} aria-label={t("runner.seekBack")}>−10</button>
    <span className="player-time">{formatAudioTime(Math.max(0, current - start))}</span>
    <input aria-label={t("runner.audioSeek")} type="range" min={0} max={length} step={0.1} value={Math.max(0, Math.min(current - start, length))} disabled={!policy.allowSeeking || unavailable} onChange={(event) => seek(start + Number(event.target.value))} />
    <span className="player-time">{unavailable ? t("runner.audioError") : state === "loading" && !duration ? t("runner.audioLoading") : formatAudioTime(length)}</span>
    <button type="button" className="player-skip" disabled={!policy.allowSeeking || unavailable} onClick={() => seek(current + 10)} aria-label={t("runner.seekForward")}>+10</button>
    <select aria-label={t("runner.speed")} value={rate} disabled={!policy.allowSpeed} onChange={(event) => { const next = Number(event.target.value); setRate(next); if (audioRef.current) audioRef.current.playbackRate = next; }}>{speeds.map((speed) => <option key={speed} value={speed}>{speed}x</option>)}</select>
    <button type="button" className="player-mute" onClick={() => { const next = !muted; setMuted(next); if (audioRef.current) audioRef.current.muted = next; }} aria-label={muted ? t("runner.unmute") : t("runner.mute")}>{muted ? "🔇" : "🔊"}</button>
    <input aria-label={t("runner.volume")} type="range" min={0} max={1} step={0.05} value={volume} onChange={(event) => { const next = Number(event.target.value); setVolume(next); if (audioRef.current) audioRef.current.volume = next; }} />
  </div>
    {clipError ? <p role="alert" className="notice notice-error">{t("runner.clipError")}</p> : state === "error" ? <p role="alert" className="notice notice-error">{t("runner.audioLoadError")}</p> : null}
    {playError ? <p role="alert" className="notice notice-error">{t("runner.audioPlayError")}</p> : null}
    {preview && !clip ? <button type="button" className="btn btn-secondary mt-2" onClick={() => { previewPending.current = false; setPreview(undefined); }}>{t("runner.fullRecording")}</button> : null}
  </>;
}
