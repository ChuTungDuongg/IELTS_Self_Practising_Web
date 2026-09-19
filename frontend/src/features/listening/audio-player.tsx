"use client";

import { useEffect, useRef, useState } from "react";

const speeds = [0.75, 1, 1.25, 1.5, 2];
export type AudioPolicy = { allowSeeking: boolean; allowSpeed: boolean };

export function ListeningAudioPlayer({ src, policy = { allowSeeking: true, allowSpeed: true } }: { src: string; policy?: AudioPolicy }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => { const audio = audioRef.current; if (!audio) return; audio.pause(); audio.load(); setPlaying(false); setCurrent(0); setDuration(0); setState("loading"); }, [src]);
  function seek(value: number) { const audio = audioRef.current; if (!audio || !policy.allowSeeking) return; audio.currentTime = value; setCurrent(value); }
  function skip(seconds: number) { seek(Math.max(0, Math.min(duration || Infinity, current + seconds))); }
  async function toggle() { const audio = audioRef.current; if (!audio) return; if (audio.paused) { await audio.play(); } else audio.pause(); }

  return <div className="listening-player" aria-label="Listening audio player"><audio ref={audioRef} src={src} preload="metadata" onLoadedMetadata={(event) => { setDuration(event.currentTarget.duration || 0); setState("ready"); }} onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onWaiting={() => setState("loading")} onCanPlay={() => setState("ready")} onError={() => setState("error")} />
    <button type="button" className="player-main" onClick={() => void toggle()} aria-label={playing ? "Pause audio" : "Play audio"}>{playing ? "❚❚" : "▶"}</button>
    <button type="button" className="player-skip" disabled={!policy.allowSeeking} onClick={() => skip(-10)} aria-label="Seek backward 10 seconds">−10</button>
    <span className="player-time">{formatTime(current)}</span>
    <input aria-label="Audio seek" type="range" min={0} max={duration || 0} step={0.1} value={Math.min(current, duration || 0)} disabled={!policy.allowSeeking || state === "error"} onChange={(event) => seek(Number(event.target.value))} />
    <span className="player-time">{state === "error" ? "Error" : state === "loading" && !duration ? "Loading" : formatTime(duration)}</span>
    <button type="button" className="player-skip" disabled={!policy.allowSeeking} onClick={() => skip(10)} aria-label="Seek forward 10 seconds">+10</button>
    <select aria-label="Playback speed" value={rate} disabled={!policy.allowSpeed} onChange={(event) => { const next = Number(event.target.value); setRate(next); if (audioRef.current) audioRef.current.playbackRate = next; }}>{speeds.map((speed) => <option key={speed} value={speed}>{speed}x</option>)}</select>
    <button type="button" className="player-mute" onClick={() => { const next = !muted; setMuted(next); if (audioRef.current) audioRef.current.muted = next; }} aria-label={muted ? "Unmute" : "Mute"}>{muted ? "🔇" : "🔊"}</button>
    <input aria-label="Volume" type="range" min={0} max={1} step={0.05} value={volume} onChange={(event) => { const next = Number(event.target.value); setVolume(next); if (audioRef.current) audioRef.current.volume = next; }} />
  </div>;
}

function formatTime(seconds: number): string { if (!Number.isFinite(seconds)) return "00:00"; const minutes = Math.floor(seconds / 60); return `${String(minutes).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`; }
