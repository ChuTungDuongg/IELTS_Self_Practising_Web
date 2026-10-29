"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

type SceneState = "static" | "ready" | "failed" | "paused" | "unavailable";
type SceneActions = { togglePause(): void; scatter(): void; retry(): void };
type MotionContext = SceneActions & {
  state: SceneState;
  paused: boolean;
  setState: Dispatch<SetStateAction<SceneState>>;
  setPaused: Dispatch<SetStateAction<boolean>>;
  connect(actions: SceneActions): () => void;
};

const GravityMotionContext = createContext<MotionContext | null>(null);

/** Mounted only on the homepage. GravityField retains ownership of the renderer. */
export function GravityMotionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SceneState>("unavailable");
  const [paused, setPaused] = useState(false);
  const controller = useRef<SceneActions | null>(null);
  const connect = useCallback((actions: SceneActions) => {
    controller.current = actions;
    return () => {
      if (controller.current !== actions) return;
      controller.current = null;
      setState("unavailable");
      setPaused(false);
    };
  }, []);
  const togglePause = useCallback(() => controller.current?.togglePause(), []);
  const scatter = useCallback(() => controller.current?.scatter(), []);
  const retry = useCallback(() => controller.current?.retry(), []);
  const value = useMemo(() => ({ state, paused, setState, setPaused, connect, togglePause, scatter, retry }), [state, paused, connect, togglePause, scatter, retry]);
  return <GravityMotionContext.Provider value={value}>{children}</GravityMotionContext.Provider>;
}

export function useGravityMotion() { return useContext(GravityMotionContext); }
