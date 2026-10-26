"use client";

import { useSyncExternalStore } from "react";

const snapshot = () => Math.floor(Date.now() / 1000);
const serverSnapshot = () => null;
function subscribe(listener: () => void) {
  const interval = window.setInterval(listener, 1000);
  document.addEventListener("visibilitychange", listener);
  return () => { window.clearInterval(interval); document.removeEventListener("visibilitychange", listener); };
}

/** Display-only wall time, re-derived from timestamps after throttling or tab suspension. */
export function useWallClockSeconds() {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
