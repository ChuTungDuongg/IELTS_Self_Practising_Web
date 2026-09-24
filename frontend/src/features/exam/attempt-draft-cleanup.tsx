"use client";

import { useEffect } from "react";
import { clearAttemptDraft } from "./exam-draft-recovery";

export function AttemptDraftCleanup({ attemptId }: { attemptId: string }) {
  useEffect(() => clearAttemptDraft(attemptId), [attemptId]);
  return null;
}
