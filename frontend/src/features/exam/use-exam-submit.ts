"use client";

import { useCallback, useRef, useState } from "react";
import { type AttemptResponse } from "@/lib/api/attempts";
import { submitAttempt } from "@/lib/api/exam";
import { AttemptStoppedError, reconcileAmbiguousSubmit } from "./attempt-lifecycle";

export function useExamSubmit({
  attemptId,
  initialAttempt,
  flush,
  runMutation,
  accept,
  isStopped,
}: {
  attemptId: string;
  initialAttempt: AttemptResponse;
  flush: () => Promise<void>;
  runMutation: <T>(mutation: () => Promise<T>) => Promise<T>;
  accept: (attempt: AttemptResponse) => void;
  isStopped: () => boolean;
}) {
  const pending = useRef(false);
  const finalizingRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    if (pending.current || isStopped()) return;
    pending.current = true;
    finalizingRef.current = true;
    setSubmitting(true);
    setFinalizing(true);
    setSubmitError(null);
    let flushed = false;
    try {
      await flush();
      flushed = true;
      await runMutation(() => submitAttempt(attemptId));
      accept({ ...initialAttempt, status: "SUBMITTED" });
    } catch (error) {
      if (error instanceof AttemptStoppedError) return;
      if (!flushed) {
        return;
      }
      const outcome = await reconcileAmbiguousSubmit(error, attemptId, accept);
      if (outcome === "terminal") return;
      setSubmitError(outcome === "unknown"
        ? "We couldn't confirm whether your submission completed. Reconnect and try again."
        : "Submission could not be completed. Please try again.");
    } finally {
      finalizingRef.current = false;
      setFinalizing(false);
      pending.current = false;
      setSubmitting(false);
    }
  }, [accept, attemptId, flush, initialAttempt, isStopped, runMutation]);

  const isFinalizing = useCallback(() => finalizingRef.current, []);
  return { submit, submitting, finalizing, submitError, isFinalizing };
}
