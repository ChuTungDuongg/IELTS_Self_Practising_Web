import { apiRequest } from "./client";

export type TimerMode = "COUNTDOWN" | "COUNT_UP";

export function startAttempt(input: {
  test_version_id: string;
  module: "READING" | "LISTENING" | "WRITING";
  timer: { mode: TimerMode; duration_seconds?: number };
}) {
  return apiRequest<{ attempt_id: string }>("/attempts", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function saveAnswer(attemptId: string, questionId: string, value: unknown) {
  return apiRequest(`/attempts/${attemptId}/answers/${questionId}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export function recordActivity(attemptId: string) {
  return apiRequest(`/attempts/${attemptId}/activity`, {
    method: "POST",
    body: JSON.stringify({ client_observed_at: new Date().toISOString() }),
  });
}

export async function deleteAttempt(attemptId: string): Promise<void> {
  await apiRequest(`/attempts/${attemptId}`, { method: "DELETE" });
}
