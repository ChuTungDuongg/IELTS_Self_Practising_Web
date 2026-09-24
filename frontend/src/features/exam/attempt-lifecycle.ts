"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getAttempt, type AttemptResponse } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { attemptDestination } from "@/features/exam/attempt-destination";
import { clearAttemptDraft, isTerminalAttempt } from "@/features/exam/exam-draft-recovery";
export { attemptDestination } from "@/features/exam/attempt-destination";

const lifecycleCodes = new Set(["ATTEMPT_FINALIZED", "ATTEMPT_EXPIRED", "ATTEMPT_PAUSED"]);
const isLifecycleError = (error: unknown) => error instanceof ApiError && lifecycleCodes.has(error.code);
const isAmbiguousSubmitError = (error: unknown) => error instanceof ApiError
  && (error.code === "NETWORK_ERROR" || error.status >= 500);

export class AttemptStoppedError extends Error {
  constructor() { super("This attempt is no longer active."); }
}

export async function reconcileAttemptError(
  error: unknown,
  attemptId: string,
  onStopped: (attempt: AttemptResponse) => void,
): Promise<boolean> {
  if (!isLifecycleError(error)) return false;
  const attempt = await getAttempt(attemptId);
  if (attempt.status === "IN_PROGRESS") return false;
  onStopped(attempt);
  return true;
}

export async function reconcileAmbiguousSubmit(
  error: unknown,
  attemptId: string,
  onStopped: (attempt: AttemptResponse) => void,
): Promise<"terminal" | "active" | "unknown" | "not-ambiguous"> {
  if (!isAmbiguousSubmitError(error)) return "not-ambiguous";
  try {
    const attempt = await getAttempt(attemptId);
    if (attempt.status === "IN_PROGRESS") return "active";
    onStopped(attempt);
    return "terminal";
  } catch {
    return "unknown";
  }
}

export function useAttemptLifecycle(attemptId: string, onStopped?: () => void) {
  const router = useRouter();
  const routerRef = useRef(router);
  const stopped = useRef(false);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const onStoppedRef = useRef(onStopped);
  const [ended, setEnded] = useState(false);
  useEffect(() => { routerRef.current = router; }, [router]);
  useEffect(() => { onStoppedRef.current = onStopped; }, [onStopped]);
  const isStopped = useCallback(() => stopped.current, []);

  const accept = useCallback((attempt: AttemptResponse) => {
    if (attempt.status === "IN_PROGRESS" || stopped.current) return;
    if (isTerminalAttempt(attempt.status)) clearAttemptDraft(attempt.attempt_id);
    stopped.current = true;
    setEnded(true);
    onStoppedRef.current?.();
    routerRef.current.push(attemptDestination(attempt));
  }, []);

  const reconcile = useCallback(async (error: unknown): Promise<boolean> => {
    if (!isLifecycleError(error)) return false;
    if (stopped.current) return true;
    if (!inFlight.current) {
      const request = reconcileAttemptError(error, attemptId, accept);
      inFlight.current = request;
      void request.finally(() => { if (inFlight.current === request) inFlight.current = null; }).catch(() => undefined);
    }
    return inFlight.current;
  }, [accept, attemptId]);

  const runMutation = useCallback(async <T,>(mutation: () => Promise<T>): Promise<T> => {
    if (stopped.current) throw new AttemptStoppedError();
    try {
      return await mutation();
    } catch (error) {
      if (await reconcile(error)) throw new AttemptStoppedError();
      throw error;
    }
  }, [reconcile]);

  return { stopped, ended, accept, reconcile, runMutation, isStopped };
}
