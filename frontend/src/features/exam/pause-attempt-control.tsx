"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { pauseAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

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
  const [error, setError] = useState<string>();

  async function confirm() {
    if (pending) return;
    setPending(true);
    setError(undefined);
    try {
      await beforePause?.();
      const attempt = await pauseAttempt(attemptId);
      router.push(attempt.status === "PAUSED" ? "/history" : `/review/${attemptId}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Your work could not be saved and paused. Please try again.");
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
