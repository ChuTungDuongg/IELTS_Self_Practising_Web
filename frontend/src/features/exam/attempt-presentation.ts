"use client";

import { useSyncExternalStore } from "react";
import type { AttemptResponse } from "@/lib/api/attempts";

export type AttemptPresentationMode = "PRACTICE" | "EXAM";
type PresentationAttempt = Pick<AttemptResponse, "attempt_id" | "module" | "test_session_id" | "attempt_context">;
const changed = "bandpilot:attempt-presentation-changed";
export const presentationStorageKey = (attemptId: string) => `bandpilot:attempt-presentation:${attemptId}`;
export const sessionPresentationStorageKey = (sessionId: string) => `bandpilot:session-presentation:${sessionId}`;

export function resolveAttemptPresentation(attempt: PresentationAttempt, preference: unknown, sessionPreference?: unknown): AttemptPresentationMode {
  if (attempt.module !== "READING" && attempt.module !== "LISTENING") return "EXAM";
  if (preference === "PRACTICE" || preference === "EXAM") return preference;
  return sessionPreference === "PRACTICE" ? "PRACTICE" : "EXAM";
}

export function rememberAttemptPresentation(attempt: PresentationAttempt, preference: AttemptPresentationMode) {
  try {
    window.localStorage.setItem(presentationStorageKey(attempt.attempt_id), resolveAttemptPresentation(attempt, preference));
    window.dispatchEvent(new Event(changed));
  } catch {
    // Storage is optional. Existing attempts remain usable in the Legacy fallback.
  }
}

export function rememberSessionPresentation(sessionId: string, preference: AttemptPresentationMode) {
  try {
    window.localStorage.setItem(sessionPresentationStorageKey(sessionId), preference);
    window.dispatchEvent(new Event(changed));
  } catch {
    // Storage is optional. Existing sessions remain usable in the Legacy fallback.
  }
}

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(changed, listener);
  return () => { window.removeEventListener("storage", listener); window.removeEventListener(changed, listener); };
}

export function useAttemptPresentation(attempt: PresentationAttempt): AttemptPresentationMode {
  return useSyncExternalStore(subscribe, () => {
    try {
      const preference = window.localStorage.getItem(presentationStorageKey(attempt.attempt_id));
      const sessionPreference = attempt.test_session_id ? window.localStorage.getItem(sessionPresentationStorageKey(attempt.test_session_id)) : null;
      return resolveAttemptPresentation(attempt, preference, sessionPreference);
    }
    catch { return "EXAM"; }
  }, () => "EXAM");
}
