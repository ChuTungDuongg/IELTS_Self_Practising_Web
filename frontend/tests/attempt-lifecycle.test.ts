import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { getAttempt, type AttemptResponse } from "@/lib/api/attempts";
import { attemptDestination, reconcileAttemptError } from "@/features/exam/attempt-lifecycle";

vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, getAttempt: vi.fn() };
});

const attemptId = "11111111-1111-4111-8111-111111111111";
const attempt = (status: AttemptResponse["status"], testSessionId: string | null = null) => ({
  attempt_id: attemptId, status, test_session_id: testSessionId,
}) as AttemptResponse;

describe("attempt lifecycle reconciliation", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each(["ATTEMPT_FINALIZED", "ATTEMPT_EXPIRED", "ATTEMPT_PAUSED"])("fetches authoritative state for %s", async (code) => {
    const resolved = attempt("INTERRUPTED");
    vi.mocked(getAttempt).mockResolvedValue(resolved);
    const onStopped = vi.fn();
    expect(await reconcileAttemptError(new ApiError(code, "finalized", 409), attemptId, onStopped)).toBe(true);
    expect(getAttempt).toHaveBeenCalledWith(attemptId);
    expect(onStopped).toHaveBeenCalledWith(resolved);
  });

  it("does not hide network, server, validation, or unrelated conflict errors", async () => {
    const onStopped = vi.fn();
    for (const error of [
      new ApiError("NETWORK_ERROR", "offline", 0),
      new ApiError("API_ERROR", "server", 500),
      new ApiError("INVALID_INPUT", "bad", 422),
      new ApiError("SOME_OTHER_CONFLICT", "conflict", 409),
    ]) expect(await reconcileAttemptError(error, attemptId, onStopped)).toBe(false);
    expect(getAttempt).not.toHaveBeenCalled();
    expect(onStopped).not.toHaveBeenCalled();
  });

  it("does not claim completion if the authoritative attempt remains active", async () => {
    vi.mocked(getAttempt).mockResolvedValue(attempt("IN_PROGRESS"));
    expect(await reconcileAttemptError(new ApiError("ATTEMPT_FINALIZED", "finalized", 409), attemptId, vi.fn())).toBe(false);
  });

  it("routes paused, standalone terminal, and full mock terminal attempts", () => {
    expect(attemptDestination(attempt("PAUSED"))).toBe("/history");
    expect(attemptDestination(attempt("INTERRUPTED"))).toBe(`/review/${attemptId}`);
    expect(attemptDestination(attempt("AUTO_SUBMITTED", "22222222-2222-4222-8222-222222222222"))).toBe("/test-session/22222222-2222-4222-8222-222222222222");
  });
});
