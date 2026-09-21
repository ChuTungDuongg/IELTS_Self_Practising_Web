"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { TestSession } from "@/lib/api/test-sessions";
import { advanceTestSession } from "@/lib/api/test-sessions";

export function TestSessionTransition({ initial }: { initial: TestSession }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const last = initial.attempts.at(-1);
  async function advance() {
    setPending(true); setError(undefined);
    try {
      const next = await advanceTestSession(initial.session_id);
      if (next.current_attempt) router.push(`/attempt/${next.current_attempt.attempt_id}`);
      else router.refresh();
    } catch { setError("Could not continue the Full Mock."); setPending(false); }
  }
  if (initial.status === "COMPLETED") return <div className="session-transition"><p className="practice-module-kicker">Full Mock complete</p><h1>{initial.test_title}</h1><p>All modules are complete. Writing may still need criterion grading before an overall band is available.</p><div className="session-score-grid">{initial.attempts.map((item) => <div key={item.attempt_id}><span>{item.module.charAt(0) + item.module.slice(1).toLowerCase()}</span><strong>{item.band_score?.toFixed(1) ?? "—"}</strong></div>)}<div><span>Overall</span><strong>{initial.overall_band_score?.toFixed(1) ?? "—"}</strong></div></div><Link className="btn btn-primary" href="/history">View results</Link></div>;
  const completedLabel = last ? formatModule(last.module) : "Module";
  const nextLabel = initial.next_module ? formatModule(initial.next_module) : "next module";
  return <div className="session-transition"><p className="practice-module-kicker">Full Mock</p><h1>{completedLabel} complete</h1><p>Next: <strong>{nextLabel}</strong></p>{initial.warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}<button type="button" className="btn btn-primary" disabled={pending} onClick={() => void advance()}>{pending ? "Preparing…" : `Continue to ${nextLabel}`}</button>{error ? <p role="alert" className="notice notice-error">{error}</p> : null}</div>;
}

function formatModule(module: "LISTENING" | "READING" | "WRITING") { return module.charAt(0) + module.slice(1).toLowerCase(); }
