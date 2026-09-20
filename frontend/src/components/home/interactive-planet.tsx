"use client";

import { useEffect, useRef, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { AppLogo } from "@/components/ui/app-logo";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const FINE_POINTER_QUERY = "(hover: hover) and (pointer: fine)";
const SETTLE_THRESHOLD = 0.001;
const EASING = 0.09;

type MotionPoint = { x: number; y: number };

const initialStyle = {
  "--planet-shift-x": "0px",
  "--planet-shift-y": "0px",
  "--orbit-rx": "0deg",
  "--orbit-ry": "0deg",
  "--ring-one-x": "0px",
  "--ring-one-y": "0px",
  "--ring-two-x": "0px",
  "--ring-two-y": "0px",
  "--star-one-x": "0px",
  "--star-one-y": "0px",
  "--star-two-x": "0px",
  "--star-two-y": "0px",
  "--glow-x": "0px",
  "--glow-y": "0px",
} as CSSProperties;

function clamp(value: number) {
  return Math.max(-1, Math.min(1, value));
}

function applyMotion(element: HTMLElement, { x, y }: MotionPoint) {
  element.style.setProperty("--planet-shift-x", `${(x * 8).toFixed(3)}px`);
  element.style.setProperty("--planet-shift-y", `${(y * 7).toFixed(3)}px`);
  element.style.setProperty("--orbit-rx", `${(y * -4).toFixed(3)}deg`);
  element.style.setProperty("--orbit-ry", `${(x * 7).toFixed(3)}deg`);
  element.style.setProperty("--ring-one-x", `${(x * 4.5).toFixed(3)}px`);
  element.style.setProperty("--ring-one-y", `${(y * 3.5).toFixed(3)}px`);
  element.style.setProperty("--ring-two-x", `${(x * -3.5).toFixed(3)}px`);
  element.style.setProperty("--ring-two-y", `${(y * -2.5).toFixed(3)}px`);
  element.style.setProperty("--star-one-x", `${(x * 13).toFixed(3)}px`);
  element.style.setProperty("--star-one-y", `${(y * 10).toFixed(3)}px`);
  element.style.setProperty("--star-two-x", `${(x * -9).toFixed(3)}px`);
  element.style.setProperty("--star-two-y", `${(y * -7).toFixed(3)}px`);
  element.style.setProperty("--glow-x", `${(x * 3).toFixed(3)}px`);
  element.style.setProperty("--glow-y", `${(y * 3).toFixed(3)}px`);
}

export function InteractivePlanet() {
  const rootRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const pressTimerRef = useRef<number | null>(null);
  const boundsRef = useRef<DOMRect | null>(null);
  const currentRef = useRef<MotionPoint>({ x: 0, y: 0 });
  const targetRef = useRef<MotionPoint>({ x: 0, y: 0 });
  const reducedMotionRef = useRef(false);
  const finePointerRef = useRef(true);

  function animate() {
    const current = currentRef.current;
    const target = targetRef.current;
    current.x += (target.x - current.x) * EASING;
    current.y += (target.y - current.y) * EASING;

    if (rootRef.current) applyMotion(rootRef.current, current);

    if (Math.abs(target.x - current.x) + Math.abs(target.y - current.y) > SETTLE_THRESHOLD) {
      frameRef.current = window.requestAnimationFrame(animate);
      return;
    }

    current.x = target.x;
    current.y = target.y;
    if (rootRef.current) applyMotion(rootRef.current, current);
    frameRef.current = null;
  }

  function startAnimation() {
    if (reducedMotionRef.current || frameRef.current !== null) return;
    frameRef.current = window.requestAnimationFrame(animate);
  }

  function resetMotion(immediate = false) {
    targetRef.current = { x: 0, y: 0 };
    boundsRef.current = null;
    rootRef.current?.classList.remove("is-active", "is-pressed");

    if (immediate) {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      currentRef.current = { x: 0, y: 0 };
      if (rootRef.current) applyMotion(rootRef.current, currentRef.current);
      return;
    }

    startAnimation();
  }

  function updateTarget(clientX: number, clientY: number) {
    const bounds = boundsRef.current;
    if (!bounds || !bounds.width || !bounds.height || !Number.isFinite(clientX) || !Number.isFinite(clientY)) return;
    targetRef.current = {
      x: clamp((clientX - (bounds.left + bounds.width / 2)) / (bounds.width / 2)),
      y: clamp((clientY - (bounds.top + bounds.height / 2)) / (bounds.height / 2)),
    };
    startAnimation();
  }

  function handlePointerEnter(event: ReactPointerEvent<HTMLDivElement>) {
    if (reducedMotionRef.current || !finePointerRef.current) return;
    boundsRef.current = event.currentTarget.getBoundingClientRect();
    event.currentTarget.classList.add("is-active");
    updateTarget(event.clientX, event.clientY);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (reducedMotionRef.current || !finePointerRef.current) return;
    updateTarget(event.clientX, event.clientY);
  }

  function handlePointerLeave() {
    resetMotion();
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (reducedMotionRef.current) return;
    const root = event.currentTarget;
    root.classList.remove("is-pressed");
    void root.offsetWidth;
    root.classList.add("is-pressed");
    if (pressTimerRef.current !== null) window.clearTimeout(pressTimerRef.current);
    pressTimerRef.current = window.setTimeout(() => {
      root.classList.remove("is-pressed");
      pressTimerRef.current = null;
    }, 400);
  }

  useEffect(() => {
    const reducedMotion = window.matchMedia(REDUCED_MOTION_QUERY);
    const finePointer = window.matchMedia(FINE_POINTER_QUERY);

    const syncPreferences = () => {
      reducedMotionRef.current = reducedMotion.matches;
      finePointerRef.current = finePointer.matches;
      if (reducedMotion.matches || !finePointer.matches) {
        targetRef.current = { x: 0, y: 0 };
        boundsRef.current = null;
        rootRef.current?.classList.remove("is-active", "is-pressed");
        if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
        currentRef.current = { x: 0, y: 0 };
        if (rootRef.current) applyMotion(rootRef.current, currentRef.current);
      }
    };

    syncPreferences();
    reducedMotion.addEventListener("change", syncPreferences);
    finePointer.addEventListener("change", syncPreferences);

    return () => {
      reducedMotion.removeEventListener("change", syncPreferences);
      finePointer.removeEventListener("change", syncPreferences);
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      if (pressTimerRef.current !== null) window.clearTimeout(pressTimerRef.current);
    };
  }, []);

  return (
    <div
      ref={rootRef}
      className="home-orbit home-orbit-interactive"
      aria-hidden="true"
      style={initialStyle}
      onPointerEnter={handlePointerEnter}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
      onPointerDown={handlePointerDown}
    >
      <div className="home-orbit-scene">
        <span className="home-orbit-glow" />
        <span className="home-orbit-ring home-orbit-ring-one" />
        <span className="home-orbit-ring home-orbit-ring-two" />
        <span className="home-orbit-core">
          <span className="home-orbit-logo"><AppLogo variant="icon" /></span>
        </span>
        <span className="home-orbit-star home-orbit-star-one" />
        <span className="home-orbit-star home-orbit-star-two" />
      </div>
    </div>
  );
}
