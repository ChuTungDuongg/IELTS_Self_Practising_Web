"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { startTestSession } from "@/lib/api/test-sessions";

export function StartFullMock({ versionId, unavailableReason, warnings = [] }: { versionId: string; unavailableReason?: string; warnings?: string[] }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  async function start() {
    setPending(true); setError(undefined);
    try {
      const result = await startTestSession(versionId);
      router.push(`/attempt/${result.current_attempt.attempt_id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start the Full Mock.");
      setPending(false);
    }
  }
  return <section className="full-mock-card"><div><p className="practice-module-kicker">Full Mock</p><h2>Listening → Reading → Writing</h2><span>Official module timing with results revealed after all three skills are complete.</span>{warnings.map((warning) => <p className="notice mt-3" key={warning}>{warning}</p>)}</div>{unavailableReason ? <p className="notice">Full Mock unavailable: {unavailableReason}</p> : <button type="button" className="btn btn-primary" disabled={pending} onClick={() => void start()}>{pending ? "Starting…" : "Start Full Mock"}</button>}{error ? <p role="alert" className="notice notice-error">{error}</p> : null}</section>;
}
