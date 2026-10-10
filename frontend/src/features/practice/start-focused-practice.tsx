"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

type FocusedTarget = { module: "READING"; unitId: string; taskNumber?: never }
  | { module: "LISTENING"; unitId: string; taskNumber?: never }
  | { module: "WRITING"; unitId: string; taskNumber: number };

export function StartFocusedPractice({ versionId, target, unavailableReason }: { versionId: string; target: FocusedTarget; unavailableReason?: string }) {
  const router = useRouter();
  const [duration, setDuration] = useState(target.module === "LISTENING" ? "600" : target.module === "WRITING" && target.taskNumber === 2 ? "2400" : "1200");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const starting = useRef(false);
  const minutes = target.module === "LISTENING" ? [10, 15, 20] : target.module === "READING" ? [20, 25, 30] : [20, 25, 30, 35, 40];

  async function start() {
    if (starting.current || unavailableReason) return;
    starting.current = true;
    setPending(true);
    setError(null);
    try {
      const result = await startAttempt({
        test_version_id: versionId, module: target.module, scope: "FOCUSED_UNIT",
        focused_unit: { kind: target.module === "READING" ? "READING_PASSAGE" : target.module === "LISTENING" ? "LISTENING_PART" : "WRITING_TASK", id: target.unitId },
        timer: duration === "count-up" ? { mode: "COUNT_UP" } : { mode: "COUNTDOWN", duration_seconds: Number(duration) },
      });
      router.push(`/attempt/${result.attempt_id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start focused practice. Please try again.");
      starting.current = false;
      setPending(false);
    }
  }

  return <div className="practice-start mt-5 border-t border-[var(--line)] pt-4">
    <label className="field-label">Practice timer
      <select className="select-field mt-2" value={duration} disabled={pending || Boolean(unavailableReason)} onChange={(event) => setDuration(event.target.value)}>
        {minutes.map((minute) => <option key={minute} value={minute * 60}>{minute} minutes</option>)}
        <option value="count-up">Count up</option>
      </select>
    </label>
    <button type="button" disabled={pending || Boolean(unavailableReason)} onClick={() => void start()} className={`btn mt-3 w-full ${target.module === "WRITING" ? "btn-writing" : target.module === "LISTENING" ? "btn-listening" : "btn-primary"}`}>
      {pending ? "Starting…" : "Start focused practice"}
    </button>
    {unavailableReason ? <p className="mt-3 text-sm text-[var(--muted)]">{unavailableReason}</p> : null}
    {error ? <p role="alert" className="notice notice-error mt-3">{error}</p> : null}
  </div>;
}
