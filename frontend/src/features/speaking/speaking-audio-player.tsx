"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSpeakingAudio, type SpeakingManifest } from "@/lib/api/speaking";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useSpeakingReplay, useSpeakingReplayController, type SpeakingReplayController } from "./speaking-audio-replay";

function SegmentAudio({ id, url, label, controller, onAttach, onReady, onError }: { id: string; url: string; label: string; controller: SpeakingReplayController; onAttach(id: string, audio: HTMLAudioElement | null): void; onReady(id: string, audio: HTMLAudioElement): void; onError(): void }) {
  const element = useRef<HTMLAudioElement | null>(null);
  const attach = useCallback((audio: HTMLAudioElement | null) => { element.current = audio; onAttach(id, audio); }, [id, onAttach]);
  useEffect(() => { if (element.current) onReady(id, element.current); }, [id, onReady]);
  return <audio ref={attach} controls preload="metadata" src={url} aria-label={label} onLoadedMetadata={event => onReady(id, event.currentTarget)} onPlay={event => controller.activate(event.currentTarget)} onPause={event => controller.pause(event.currentTarget)} onTimeUpdate={event => controller.update(event.currentTarget)} onSeeked={event => controller.update(event.currentTarget)} onRateChange={event => controller.update(event.currentTarget)} onEnded={event => controller.release(event.currentTarget)} onError={event => { controller.release(event.currentTarget); onError(); }} />;
}

export function SpeakingAudioPlayer({ segments, response }: Pick<SpeakingManifest, "segments"> & Partial<Pick<SpeakingManifest, "response">>) {
  const { t } = useTranslation(); const replay = useSpeakingReplay(); const controller = useSpeakingReplayController();
  const [urls, setUrls] = useState<Record<string, string>>({}); const [error, setError] = useState(false); const [loading, setLoading] = useState(false);
  const mounted = useRef(true); const cache = useRef(new Map<string, string>()); const pending = useRef(new Map<string, Promise<void>>());
  const elements = useRef(new Map<string, HTMLAudioElement>()); const root = useRef<HTMLDivElement>(null); const handled = useRef<number | null>(null);
  const attachAudio = useCallback((id: string, audio: HTMLAudioElement | null) => {
    if (audio) elements.current.set(id, audio);
    else { const previous = elements.current.get(id); if (previous) controller.release(previous); elements.current.delete(id); }
  }, [controller]);
  useEffect(() => {
    mounted.current = true;
    const audioElements = elements.current; const cachedUrls = cache.current;
    return () => { mounted.current = false; for (const audio of audioElements.values()) controller.release(audio); for (const url of cachedUrls.values()) URL.revokeObjectURL(url); cachedUrls.clear(); };
  }, [controller]);
  const loadSegment = useCallback((segment: SpeakingManifest["segments"][number]) => {
    if (cache.current.has(segment.id)) return Promise.resolve();
    const existing = pending.current.get(segment.id); if (existing) return existing;
    const download = (async () => {
      if (!segment.content_url || !segment.chunks.length) return;
      const blob = await fetchSpeakingAudio(segment.content_url); if (!mounted.current) return;
      const url = URL.createObjectURL(blob); cache.current.set(segment.id, url); setUrls(previous => ({ ...previous, [segment.id]: url }));
    })().finally(() => pending.current.delete(segment.id));
    pending.current.set(segment.id, download); return download;
  }, []);
  const request = replay?.request;
  const target = request && response?.id === request.span.response_id && response.active_take_number === request.span.take_number ? segments.find(segment => segment.id === request.span.segment_id) : undefined;
  useEffect(() => {
    if (!target || !request || !controller.isCurrent(request.id)) return;
    const details = root.current?.closest("details"); if (details) details.open = true;
    let cancelled = false;
    void Promise.resolve().then(async () => {
      if (cancelled || !mounted.current) return;
      setLoading(true); setError(false); await loadSegment(target);
    }).catch(() => { if (!cancelled && mounted.current) setError(true); }).finally(() => { if (!cancelled && mounted.current) setLoading(false); });
    return () => { cancelled = true; };
  }, [target, request, controller, loadSegment]);
  const tryReplay = useCallback((segmentId: string, audio: HTMLAudioElement) => {
    if (!request || target?.id !== segmentId || !controller.isCurrent(request.id) || handled.current === request.id || audio.readyState < 1) return;
    handled.current = request.id;
    void controller.replay(audio, request.span, request.id).catch(() => { if (mounted.current && controller.isCurrent(request.id)) { controller.stop(); setError(true); } });
  }, [controller, request, target]);
  async function load() {
    setLoading(true); setError(false);
    try { for (const segment of segments) await loadSegment(segment); }
    catch { if (mounted.current) setError(true); }
    finally { if (mounted.current) setLoading(false); }
  }
  const available = segments.filter(segment => segment.content_url && segment.chunks.length);
  return <div ref={root} id={response ? `speaking-response-${response.id}` : undefined} className="speaking-audio-player" aria-busy={loading}>
    {available.some(segment => !urls[segment.id]) ? <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void load()}>{t(loading ? "speakingRuntime.loadingAudio" : "speakingRuntime.loadAudio")}</button> : !available.length ? <button type="button" className="btn btn-secondary" disabled>{t("speakingRuntime.loadAudio")}</button> : null}
    {segments.map((segment, index) => urls[segment.id] ? <SegmentAudio key={segment.id} id={segment.id} url={urls[segment.id]} label={t("speakingRuntime.segment", { number: index + 1 })} controller={controller} onAttach={attachAudio} onReady={tryReplay} onError={() => setError(true)} /> : null)}
    {error ? <p role="alert" className="notice notice-error">{t("speakingRuntime.audioError")}</p> : null}
  </div>;
}
