"use client";

import { useCallback, useRef, useState } from "react";
import { speakingAudioUrl } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./lab.module.css";

export type AudioWindow = { start_ms: number; end_ms: number };
export function useSourcePlayback() {
  const audioRef = useRef<HTMLAudioElement>(null); const windows = useRef<AudioWindow[]>([]);
  const [error, setError] = useState(false);
  const attachAudio = useCallback((node: HTMLAudioElement | null) => { audioRef.current = node; }, []);
  const stop = useCallback(() => { windows.current = []; audioRef.current?.pause(); }, []);
  const play = useCallback((items: AudioWindow[]) => {
    const audio = audioRef.current; if (!audio || !items.length) return;
    windows.current = [...items]; setError(false);
    audio.currentTime = items[0].start_ms / 1000;
    void audio.play().catch(() => setError(true));
  }, []);
  const seek = useCallback((ms: number) => { windows.current = []; if (audioRef.current) audioRef.current.currentTime = ms / 1000; }, []);
  const advance = useCallback(() => {
    const audio = audioRef.current; const current = windows.current[0]; if (!audio || !current) return;
    if (audio.currentTime * 1000 >= current.end_ms || audio.currentTime * 1000 < current.start_ms - 100) {
      windows.current.shift(); const next = windows.current[0];
      if (next) { audio.currentTime = next.start_ms / 1000; void audio.play().catch(() => setError(true)); } else audio.pause();
    }
  }, []);
  return { attachAudio, play, stop, seek, advance, error, setError };
}

export function AudioReviewPlayer({ sampleId, durationMs, playback }: { sampleId: string; durationMs: number; playback: ReturnType<typeof useSourcePlayback> }) {
  const { t } = useTranslation(); const [at, setAt] = useState(0);
  return <section className={styles.panel} aria-label={t("speakingLab.original")}>
    <h2>{t("speakingLab.original")}</h2><p className={styles.muted}>{t("speakingLab.windowHelp")}</p>
    <audio ref={node => playback.attachAudio(node)} className={styles.audio} controls preload="metadata" crossOrigin="use-credentials" src={speakingAudioUrl(sampleId)} onTimeUpdate={playback.advance} onEnded={playback.stop} onError={() => playback.setError(true)} />
    <div className={styles.actions}><label>{t("speakingLab.seek")} <input className="field" aria-label={t("speakingLab.seek")} type="number" min={0} max={durationMs / 1000} step={0.1} value={at} onChange={e => setAt(Number(e.target.value))} /></label><button className="btn btn-secondary" onClick={() => playback.seek(Math.max(0, Math.min(durationMs, at * 1000)))}>{t("speakingLab.seekAction")}</button><button className="btn btn-secondary" onClick={playback.stop}>{t("speakingLab.stop")}</button></div>
    {playback.error && <p role="alert" className="notice notice-error">{t("speakingLab.playbackFailed")}</p>}
  </section>;
}
