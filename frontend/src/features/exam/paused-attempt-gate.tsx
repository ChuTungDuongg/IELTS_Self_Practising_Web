"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatDuration } from "@/features/exam/timer";
import { resumeAttempt, type AttemptResponse } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

export function PausedAttemptGate({ attempt, testTitle }: { attempt: AttemptResponse; testTitle: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  async function resume() {
    if (pending) return;
    setPending(true);
    setError(undefined);
    try {
      await resumeAttempt(attempt.attempt_id);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "This attempt could not be resumed. Please try again.");
      setPending(false);
    }
  }

  const frozenTime = attempt.timer_mode === "COUNTDOWN"
    ? `Remaining: ${formatDuration(attempt.remaining_seconds ?? 0)}`
    : `Practice time: ${formatDuration(attempt.elapsed_seconds)}`;

  return <main className="paused-attempt-gate">
    <p className="page-eyebrow">{attempt.module} · PAUSED</p>
    <h1>Attempt paused</h1>
    <p>{testTitle}</p>
    <p>Your progress is saved.</p>
    <strong>{frozenTime}</strong>
    {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
    <div>
      <button type="button" className="btn btn-primary" disabled={pending} onClick={() => void resume()}>{pending ? "Resuming…" : "Resume attempt"}</button>
      <Link href="/history" className="btn btn-secondary">Back to history</Link>
    </div>
  </main>;
}
