import type { AttemptResponse } from "@/lib/api/attempts";

export function attemptDestination(attempt: AttemptResponse): string {
  if (attempt.status === "PAUSED") return "/history";
  if (attempt.test_session_id) return `/test-session/${attempt.test_session_id}`;
  return `/review/${attempt.attempt_id}`;
}
