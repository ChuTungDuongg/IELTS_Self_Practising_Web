"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { pauseAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { AttemptStoppedError, attemptDestination, reconcileAttemptError } from "@/features/exam/attempt-lifecycle";

export function PauseAttemptControl({
  attemptId,
  beforePause,
}: {
  attemptId: string;
  beforePause?: () => Promise<void>;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [error, setError] = useState<string>();

  async function confirm() {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError(undefined);
    try {
      await beforePause?.();
      const attempt = await pauseAttempt(attemptId);
      router.push(attemptDestination(attempt));
    } catch (caught) {
      if (caught instanceof AttemptStoppedError) return;
      try {
        if (await reconcileAttemptError(caught, attemptId, (attempt) => router.push(attemptDestination(attempt)))) return;
      } catch (reconcileError) {
        caught = reconcileError;
      }
      setError(caught instanceof ApiError ? caught.message : "Your work could not be saved and paused. Please try again.");
      pendingRef.current = false;
      setPending(false);
    }
  }

  return (
    <>
      <button type="button" className="exam-pause-button" onClick={() => setOpen(true)}>
        Pause &amp; exit
      </button>
      <ConfirmDialog
        open={open}
        title="Pause this attempt?"
        description="Your progress will be saved and the timer will stop until you resume from Attempt History."
        confirmLabel="Pause & exit"
        pending={pending}
        errorMessage={error}
        onCancel={() => { setOpen(false); setError(undefined); }}
        onConfirm={() => void confirm()}
      />
    </>
  );
}
