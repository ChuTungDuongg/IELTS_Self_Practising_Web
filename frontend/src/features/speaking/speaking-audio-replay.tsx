"use client";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { SpeakingAudioSpan } from "@/lib/api/speaking-ai";
import type { SpeakingReviewData } from "@/lib/api/speaking";

/** One controller per review, shared by native recording controls and feedback replay. */
export class SpeakingReplayController {
  private active: HTMLAudioElement | null = null;
  private bound: { audio: HTMLAudioElement; end: number } | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private generation = 0;
  private clearTimer() { if (this.timer) clearTimeout(this.timer); this.timer = null; }
  beginRequest() { this.stop(); return this.generation; }
  isCurrent(id: number) { return this.generation === id; }
  activate(audio: HTMLAudioElement) {
    if (this.active !== audio) { this.stop(); this.active = audio; }
    this.update(audio);
  }
  async replay(audio: HTMLAudioElement, span: SpeakingAudioSpan, id: number) {
    if (!this.isCurrent(id)) return;
    const knownDuration = Number.isFinite(audio.duration) && audio.duration > 0;
    if (knownDuration && span.start_ms / 1000 >= audio.duration) throw new Error("SPEAKING_MEDIA_INVALID");
    const start = Math.max(0, span.start_ms / 1000 - .5);
    // MediaRecorder WebM may have no duration header. The validated endpoint is
    // still safe; omit trailing context until the source duration is known.
    const end = knownDuration ? Math.min(audio.duration, span.end_ms / 1000 + .5) : span.end_ms / 1000;
    this.active = audio; this.bound = { audio, end }; audio.currentTime = start;
    await audio.play();
    if (this.isCurrent(id)) this.update(audio);
  }
  update(audio: HTMLAudioElement) {
    if (this.bound?.audio !== audio) return;
    this.clearTimer();
    const remaining = this.bound.end - audio.currentTime;
    if (remaining <= 0) { this.stop(); return; }
    if (!audio.paused && audio.playbackRate > 0) this.timer = setTimeout(() => this.update(audio), Math.max(10, remaining * 1000 / audio.playbackRate));
  }
  pause(audio: HTMLAudioElement) { if (this.active === audio) this.clearTimer(); }
  release(audio: HTMLAudioElement) { if (this.active === audio) this.stop(); }
  stop() {
    this.generation++; this.clearTimer(); this.bound = null;
    const previous = this.active; this.active = null; previous?.pause();
  }
}

type ReplayRequest = { id: number; span: SpeakingAudioSpan };
type ReplayContext = { controller: SpeakingReplayController; request: ReplayRequest | null; canReplay(span: SpeakingAudioSpan): boolean; replay(span: SpeakingAudioSpan): void };
const Context = createContext<ReplayContext | null>(null);
export function SpeakingReplayProvider({ data, children }: { data: SpeakingReviewData; children: ReactNode }) {
  const [controller] = useState(() => new SpeakingReplayController());
  const [request, setRequest] = useState<ReplayRequest | null>(null);
  useEffect(() => () => controller.stop(), [controller]);
  const value = useMemo<ReplayContext>(() => {
    const canReplay = (span: SpeakingAudioSpan) => data.parts.some(part => part.responses.some(item => item.response.id === span.response_id && item.response.active_take_number === span.take_number && item.segments.some(segment => segment.id === span.segment_id && segment.content_url && segment.chunks.length)));
    return { controller, request, canReplay, replay: span => { if (canReplay(span)) setRequest({ id: controller.beginRequest(), span }); } };
  }, [controller, data, request]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useSpeakingReplay() { return useContext(Context); }

/** Standalone recorder preview players still get exclusive playback within their own player. */
export function useSpeakingReplayController() {
  const shared = useSpeakingReplay();
  const [local] = useState(() => new SpeakingReplayController());
  useEffect(() => () => local.stop(), [local]);
  return shared?.controller ?? local;
}
