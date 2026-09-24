"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { AttemptResponse } from "@/lib/api/attempts";
import { attemptDestination } from "./attempt-destination";
import { clearAttemptDraft } from "./exam-draft-recovery";

export function TerminalAttemptRedirect({ attempt }: { attempt: AttemptResponse }) {
  const router = useRouter();
  useEffect(() => {
    clearAttemptDraft(attempt.attempt_id);
    router.replace(attemptDestination(attempt));
  }, [attempt, router]);
  return <p role="status">Attempt finished. Opening your result…</p>;
}
