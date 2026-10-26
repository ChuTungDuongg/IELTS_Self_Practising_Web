"use client";

import { useSyncExternalStore } from "react";
import type { AttemptResponse } from "@/lib/api/attempts";

export type AttemptPresentationMode = "PRACTICE" | "EXAM";
type PresentationAttempt = Pick<AttemptResponse, "attempt_id" | "module" | "test_session_id" | "attempt_context">;
const changed = "bandpilot:attempt-presentation-changed";
export const presentationStorageKey = (attemptId: string) => `bandpilot:attempt-presentation:${attemptId}`;

export function resolveAttemptPresentation(attempt: PresentationAttempt, preference: unknown): AttemptPresentationMode {
  if (attempt.test_session_id || attempt.attempt_context === "FULL_MOCK") return "EXAM";
  return (attempt.module === "READING" || attempt.module === "LISTENING") && preference === "PRACTICE" ? "PRACTICE" : "EXAM";
}

export function rememberAttemptPresentation(attempt: PresentationAttempt, preference: AttemptPresentationMode) {
  try {
    window.localStorage.setItem(presentationStorageKey(attempt.attempt_id), resolveAttemptPresentation(attempt, preference));
    window.dispatchEvent(new Event(changed));
  } catch {
    // Storage is optional. Existing attempts remain usable in the Exam fallback.
  }
}

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(changed, listener);
  return () => { window.removeEventListener("storage", listener); window.removeEventListener(changed, listener); };
}

export function useAttemptPresentation(attempt: PresentationAttempt): AttemptPresentationMode {
  return useSyncExternalStore(subscribe, () => {
    try { return resolveAttemptPresentation(attempt, window.localStorage.getItem(presentationStorageKey(attempt.attempt_id))); }
    catch { return "EXAM"; }
  }, () => "EXAM");
}
