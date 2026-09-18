"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

const choices = [
  ["70 minutes", 4200], ["60 minutes", 3600], ["50 minutes", 3000], ["40 minutes", 2400],
] as const;

export function StartAttempt({ versionId }: { versionId: string }) {
  const router = useRouter();
  const [duration, setDuration] = useState<string>("3600");
  const [error, setError] = useState<string | null>(null);
  async function start() {
    try {
      const countUp = duration === "unlimited";
      const result = await startAttempt({ test_version_id: versionId, module: "READING", timer: countUp ? { mode: "COUNT_UP" } : { mode: "COUNTDOWN", duration_seconds: Number(duration) } });
      router.push(`/attempt/${result.attempt_id}`);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Could not start attempt."); }
  }
  return <div className="mt-5 border-t border-[var(--line)] pt-4"><label className="text-sm font-medium">Timer <select value={duration} onChange={(event) => setDuration(event.target.value)} className="ml-2 rounded-md border border-[var(--line)] px-2 py-1">{choices.map(([label, seconds]) => <option key={seconds} value={seconds}>{label}</option>)}<option value="unlimited">Unlimited · Count up</option></select></label><button onClick={start} className="ml-3 rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white">Start Reading</button>{error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}</div>;
}
