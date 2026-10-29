"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { backgroundStage, modes } from "./physics";
import { loadGravityScene } from "./load-scene";
import { crossedStorySnap, storyPosition } from "./story-progress";
import type { GravityScene } from "./scene";
import { useGravityMotion } from "./gravity-motion-provider";

const fallbackSpheres = Array.from({ length: 20 }, (_, i) => ({
  left: `${12 + (i * 37 % 76)}%`, top: `${10 + (i * 23 % 55)}%`,
  width: `${42 + i * 17 % 96}px`, aspectRatio: "1", "--sphere-depth": String(i % 5),
}));

/** Progressive enhancement only: SSR content and the static field need no WebGL. */
export function GravityField() {
  const { t } = useTranslation();
  const motion = useGravityMotion();
  const state = motion?.state ?? "static";
  const paused = motion?.paused ?? false;
  const connect = motion?.connect, setState = motion?.setState, setPaused = motion?.setPaused;
  const root = useRef<HTMLDivElement>(null);
  const controller = useRef<GravityScene | null>(null);
  const pausedRef = useRef(false);
  const allowDataRef = useRef(false);
  const syncActivityRef = useRef<() => void>(() => undefined);
  const initializeRef = useRef<() => void>(() => undefined);
  const navigateRef = useRef<((index: number) => void) | null>(null);
  const [activeSection, setActiveSection] = useState(0);

  useEffect(() => {
    const element = root.current, story = element?.closest<HTMLElement>(".gravity-story");
    if (!element || !story || !connect || !setState || !setPaused) return;
    if (typeof ResizeObserver === "undefined") { setState("unavailable"); return; }
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    const dataConnection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    const documentRoot = document.documentElement;
    const header = document.querySelector<HTMLElement>(".app-header");
    let aborted = false, inView = true, generation = 0;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let snapTimer: ReturnType<typeof setTimeout> | undefined;
    let navigationTimer: ReturnType<typeof setTimeout> | undefined;
    let scrollFrame = 0;
    let previousScrollY = window.scrollY;
    let pendingSnap: { index: number; top: number } | null = null;
    let pendingDirection = 0;
    let navigating = false;
    let navigatingIndex: number | null = null;
    const headerHeight = () => document.querySelector<HTMLElement>(".app-header")?.getBoundingClientRect().height ?? 0;
    const sections = () => [...story.querySelectorAll<HTMLElement>("[data-gravity-section]")];
    const anchors = () => sections().map(section => Math.max(0, window.scrollY + section.getBoundingClientRect().top - headerHeight() - 16));
    const visible = () => inView && !document.hidden && !pausedRef.current;
    const syncActivity = () => controller.current?.setActive(visible());
    syncActivityRef.current = syncActivity;
    const progress = () => {
      scrollFrame = 0;
      const chapterSections = sections();
      const top = story.getBoundingClientRect().top;
      documentRoot.style.setProperty("--gravity-header-height", `${headerHeight()}px`);
      const offset = Math.max(0, -top);
      const { progress: value, active } = storyPosition(offset, element.clientHeight || window.innerHeight,
        chapterSections.map(section => ({ start: section.offsetTop, height: section.offsetHeight })));
      const displayedSection = navigatingIndex ?? active;
      setActiveSection(previous => previous === displayedSection ? previous : displayedSection);
      story.dataset.stage = String(backgroundStage(value));
      story.dataset.section = String(active);
      const phase = modes(value);
      story.style.setProperty("--gravity-lime", String(phase.lime));
      story.style.setProperty("--gravity-pink", String(phase.pink));
      story.style.setProperty("--gravity-hero", String(phase.hero));
      controller.current?.setProgress(value);
    };
    const finishNavigation = () => {
      clearTimeout(navigationTimer);
      navigationTimer = setTimeout(() => { navigating = false; navigatingIndex = null; progress(); }, 240);
    };
    const scrollToChapter = (index: number, top: number) => {
      clearTimeout(snapTimer); pendingSnap = null;
      navigating = true; navigatingIndex = index;
      setActiveSection(index);
      window.scrollTo({ top, behavior: reduced ? "auto" : "smooth" });
      finishNavigation();
    };
    navigateRef.current = index => {
      const top = anchors()[index];
      if (top !== undefined) scrollToChapter(index, top);
    };
    const interruptNavigation = () => {
      if (!navigating) return;
      clearTimeout(navigationTimer); navigating = false; navigatingIndex = null;
    };
    const onScroll = () => {
      const currentY = window.scrollY;
      const direction = Math.sign(currentY - previousScrollY);
      if (navigating) {
        finishNavigation();
      } else if (direction) {
        const bounds = story.getBoundingClientRect();
        if (bounds.bottom > headerHeight() && bounds.top < window.innerHeight) {
          if (pendingDirection && direction !== pendingDirection) pendingSnap = null;
          pendingDirection = direction;
          const crossed = crossedStorySnap(previousScrollY, currentY, anchors(), window.innerHeight * .42);
          if (crossed) pendingSnap = crossed;
          clearTimeout(snapTimer);
          if (pendingSnap && Math.abs(currentY - pendingSnap.top) <= window.innerHeight * .75) {
            snapTimer = setTimeout(() => {
              if (pendingSnap) scrollToChapter(pendingSnap.index, pendingSnap.top);
            }, 180);
          } else pendingSnap = null;
        } else {
          clearTimeout(snapTimer); pendingSnap = null;
        }
      }
      previousScrollY = currentY;
      if (!scrollFrame) scrollFrame = requestAnimationFrame(progress);
    };
    const initialize = async () => {
      const current = ++generation;
      controller.current?.dispose(); controller.current = null;
      setState("static");
      // Autoplay is requested for this homepage. Save-Data still requires explicit opt-in.
      if (dataConnection?.saveData && !allowDataRef.current) {
        pausedRef.current = true; setPaused(true); setState("paused"); return;
      }
      if (pausedRef.current) { setState("paused"); return; }
      timeout = setTimeout(() => {
        // A refresh below the story must not time out a deliberately suspended renderer.
        if (current === generation && visible()) { generation++; controller.current?.dispose(); controller.current = null; setState("failed"); }
      }, 8000);
      try {
        const { createGravityScene } = await loadGravityScene();
        if (aborted || current !== generation) return;
        const lowPower = reduced || (navigator.hardwareConcurrency || 8) <= 4;
        controller.current = createGravityScene(element, lowPower,
          () => { if (!aborted && current === generation) { clearTimeout(timeout); setState("ready"); } },
          () => { if (!aborted && current === generation) { clearTimeout(timeout); setState("failed"); controller.current?.dispose(); controller.current = null; } });
        progress(); syncActivity();
      } catch {
        if (!aborted && current === generation) { clearTimeout(timeout); setState("failed"); }
      }
    };
    initializeRef.current = () => { void initialize(); };
    const disconnectControls = connect({
      togglePause() {
        const next = !pausedRef.current; pausedRef.current = next; setPaused(next);
        if (!controller.current && !next) { allowDataRef.current = true; initializeRef.current(); }
        else syncActivityRef.current();
      },
      scatter() { if (!pausedRef.current) controller.current?.scatter(); },
      retry() { pausedRef.current = false; setPaused(false); initializeRef.current(); },
    });
    const intersection = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; syncActivity(); });
    intersection?.observe(story);
    const resizeObserver = new ResizeObserver(onScroll); resizeObserver.observe(story); if (header) resizeObserver.observe(header);
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
    window.addEventListener("wheel", interruptNavigation, { passive: true });
    window.addEventListener("touchstart", interruptNavigation, { passive: true });
    document.addEventListener("visibilitychange", syncActivity);
    window.addEventListener("blur", leave);
    story.addEventListener("pointermove", pointer, { passive: true });
    story.addEventListener("pointerdown", pointer, { passive: true });
    story.addEventListener("pointerup", release, { passive: true });
    story.addEventListener("pointercancel", leave); story.addEventListener("pointerleave", leave);
    progress(); void initialize();
    return () => {
      disconnectControls();
      aborted = true; generation++; clearTimeout(timeout); clearTimeout(snapTimer); clearTimeout(navigationTimer); cancelAnimationFrame(scrollFrame);
      intersection?.disconnect(); resizeObserver.disconnect();
      window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); window.removeEventListener("blur", leave);
      window.removeEventListener("wheel", interruptNavigation); window.removeEventListener("touchstart", interruptNavigation);
      document.removeEventListener("visibilitychange", syncActivity);
      story.removeEventListener("pointermove", pointer); story.removeEventListener("pointerdown", pointer);
      story.removeEventListener("pointerup", release); story.removeEventListener("pointercancel", leave); story.removeEventListener("pointerleave", leave);
      controller.current?.dispose(); controller.current = null;
      documentRoot.style.removeProperty("--gravity-header-height");
      syncActivityRef.current = () => undefined;
      initializeRef.current = () => undefined;
      navigateRef.current = null;
    };
  }, [connect, setPaused, setState]);

  function navigateSection(index: number) {
    if (navigateRef.current) { navigateRef.current(index); return; }
    const section = root.current?.closest(".gravity-story")?.querySelectorAll<HTMLElement>("[data-gravity-section]")[index];
    if (!section) return;
    const header = document.querySelector(".app-header")?.getBoundingClientRect().height ?? 0;
    setActiveSection(index);
    window.scrollTo({ top: Math.max(0, window.scrollY + section.getBoundingClientRect().top - header - 16), behavior: "smooth" });
  }

  return <>
    <div className="gravity-stage" data-scene={state} data-motion-paused={paused}>
      <div className="gravity-art" aria-hidden="true">
      <div className="gravity-gradient gravity-gradient-blue" /><div className="gravity-gradient gravity-gradient-lime" /><div className="gravity-gradient gravity-gradient-pink" />
      <div className="gravity-static-field">{fallbackSpheres.map((style, i) => <span key={i} className={`gravity-static-sphere sphere-${i % 5}`} style={style as React.CSSProperties} />)}</div>
      <div ref={root} className="gravity-webgl" />
      </div>
    </div>
    <div className="gravity-tools">
      <nav className="gravity-phase-nav" aria-label={t("gravity.scroll")}>
        {(["gravity-title", "gravity-skills-title", "gravity-shape-title", "gravity-release-title"] as const).map((id, index) => <a href={`#${id}`} key={id} aria-current={activeSection === index ? "step" : undefined} onClick={event => { event.preventDefault(); navigateSection(index); }} aria-label={`${index + 1}. ${t((["gravity.heroOne", "gravity.skillsTitle", "gravity.reviewTitle", "gravity.mockOne"] as const)[index])}`}>{String(index + 1).padStart(2, "0")}</a>)}
      </nav>
    </div>
  </>;
}
