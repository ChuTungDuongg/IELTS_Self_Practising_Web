"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { backgroundStage } from "./physics";
import { loadGravityScene } from "./load-scene";
import type { GravityScene } from "./scene";

const fallbackSpheres = Array.from({ length: 20 }, (_, i) => ({
  left: `${12 + (i * 37 % 76)}%`, top: `${10 + (i * 23 % 55)}%`,
  width: `${42 + i * 17 % 96}px`, aspectRatio: "1", "--sphere-depth": String(i % 5),
}));

/** Progressive enhancement only: SSR content and the static field need no WebGL. */
export function GravityField() {
  const { t } = useTranslation();
  const root = useRef<HTMLDivElement>(null);
  const controller = useRef<GravityScene | null>(null);
  const pausedRef = useRef(false);
  const syncActivityRef = useRef<() => void>(() => undefined);
  const initializeRef = useRef<() => void>(() => undefined);
  const [paused, setPaused] = useState(false);
  const [state, setState] = useState<"static" | "ready" | "failed" | "paused">("static");
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const element = root.current, story = element?.closest<HTMLElement>(".gravity-story");
    if (!element || !story || typeof window.matchMedia !== "function" || typeof ResizeObserver === "undefined") return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const dataConnection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    let aborted = false, inView = true, generation = 0;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let scrollFrame = 0;
    const visible = () => inView && !document.hidden && !pausedRef.current;
    const syncActivity = () => controller.current?.setActive(visible());
    syncActivityRef.current = syncActivity;
    const progress = () => {
      scrollFrame = 0;
      const sections = [...story.querySelectorAll<HTMLElement>("[data-gravity-section]")];
      const top = story.getBoundingClientRect().top;
      const offset = Math.max(0, -top);
      let value = 0;
      for (let index = 0; index < sections.length; index++) {
        const start = sections[index].offsetTop;
        if (offset >= start) value = index + Math.min(1, (offset - start) / Math.max(1, sections[index].offsetHeight));
      }
      story.dataset.stage = String(backgroundStage(value));
      controller.current?.setProgress(value);
    };
    const onScroll = () => { if (!scrollFrame) scrollFrame = requestAnimationFrame(progress); };
    const initialize = async () => {
      const current = ++generation;
      controller.current?.dispose(); controller.current = null;
      setState("static"); setReduced(motion.matches);
      // Save-data users keep the complete static composition without downloading Three.js.
      if (motion.matches || dataConnection?.saveData) return;
      if (pausedRef.current) { setState("paused"); return; }
      timeout = setTimeout(() => { if (current === generation) { generation++; controller.current?.dispose(); controller.current = null; setState("failed"); } }, 8000);
      try {
        const { createGravityScene } = await loadGravityScene();
        if (aborted || current !== generation) return;
        const lowPower = (navigator.hardwareConcurrency || 8) <= 4;
        controller.current = createGravityScene(element, lowPower,
          () => { if (!aborted && current === generation) { clearTimeout(timeout); setState("ready"); } },
          () => { if (!aborted && current === generation) { clearTimeout(timeout); setState("failed"); controller.current?.dispose(); controller.current = null; } });
        progress(); syncActivity();
      } catch {
        if (!aborted && current === generation) { clearTimeout(timeout); setState("failed"); }
      }
    };
    initializeRef.current = () => { void initialize(); };
    const preferencesChanged = () => { clearTimeout(timeout); void initialize(); };
    const intersection = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; syncActivity(); });
    intersection?.observe(story);
    const resizeObserver = new ResizeObserver(onScroll); resizeObserver.observe(story);
    const updatePointer = (event: PointerEvent, down: boolean) => {
      const bounds = element.getBoundingClientRect();
      controller.current?.setPointer((event.clientX - bounds.left) / Math.max(1, bounds.width) * 2 - 1, -(event.clientY - bounds.top) / Math.max(1, bounds.height) * 2 + 1, down, true);
    };
    const pointer = (event: PointerEvent) => {
      if ((event.target as HTMLElement).closest("a, button, input, select, textarea")) return;
      updatePointer(event, event.buttons > 0);
    };
    const leave = () => controller.current?.setPointer(99, 99, false, false);
    const release = (event: PointerEvent) => { if (event.pointerType === "touch") leave(); else updatePointer(event, false); };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    document.addEventListener("visibilitychange", syncActivity);
    window.addEventListener("blur", leave);
    story.addEventListener("pointermove", pointer, { passive: true });
    story.addEventListener("pointerdown", pointer, { passive: true });
    story.addEventListener("pointerup", release, { passive: true });
    story.addEventListener("pointercancel", leave); story.addEventListener("pointerleave", leave);
    motion.addEventListener("change", preferencesChanged);
    progress(); void initialize();
    return () => {
      aborted = true; generation++; clearTimeout(timeout); cancelAnimationFrame(scrollFrame);
      intersection?.disconnect(); resizeObserver.disconnect(); motion.removeEventListener("change", preferencesChanged);
      window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); window.removeEventListener("blur", leave);
      document.removeEventListener("visibilitychange", syncActivity);
      story.removeEventListener("pointermove", pointer); story.removeEventListener("pointerdown", pointer);
      story.removeEventListener("pointerup", release); story.removeEventListener("pointercancel", leave); story.removeEventListener("pointerleave", leave);
      controller.current?.dispose(); controller.current = null;
      syncActivityRef.current = () => undefined;
      initializeRef.current = () => undefined;
    };
  }, []);

  function togglePause() {
    const next = !pausedRef.current; pausedRef.current = next; setPaused(next);
    if (!controller.current && !next) initializeRef.current();
    else syncActivityRef.current();
  }

  return <>
    <div className="gravity-stage" data-scene={state} aria-hidden="true">
      <div className="gravity-gradient gravity-gradient-blue" /><div className="gravity-gradient gravity-gradient-lime" /><div className="gravity-gradient gravity-gradient-pink" />
      <div className="gravity-static-field">{fallbackSpheres.map((style, i) => <span key={i} className={`gravity-static-sphere sphere-${i % 5}`} style={style as React.CSSProperties} />)}</div>
      <div ref={root} className="gravity-webgl" />
    </div>
    <div className="gravity-motion-controls">
      {(state === "ready" || state === "paused") && !reduced ? <><button type="button" className="gravity-control" aria-pressed={paused} onClick={togglePause}>{t(paused ? "gravity.play" : "gravity.pause")}</button><button type="button" className="gravity-control" disabled={paused} onClick={() => controller.current?.scatter()}>{t("gravity.scatter")}</button></> : <span className="gravity-scene-note">{t("gravity.still")}</span>}
    </div>
  </>;
}
