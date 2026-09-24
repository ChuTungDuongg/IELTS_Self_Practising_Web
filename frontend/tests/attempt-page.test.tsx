import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AttemptShellPage from "@/app/attempt/[attemptId]/page";
import { getExam } from "@/lib/api/exam";
import { ApiError } from "@/lib/api/client";
import { draftStorageKey } from "@/features/exam/exam-draft-recovery";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`); }),
  notFound: vi.fn(() => { throw new Error("notFound"); }),
  useRouter: () => ({ replace }),
}));
vi.mock("@/lib/api/exam", () => ({ getExam: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));
vi.mock("@/features/reading/reading-runner", () => ({ ReadingRunner: () => null }));
vi.mock("@/features/listening/listening-runner", () => ({ ListeningRunner: () => null }));
vi.mock("@/features/writing/writing-runner", () => ({ WritingRunner: () => null }));
vi.mock("@/features/exam/paused-attempt-gate", () => ({ PausedAttemptGate: () => null }));

const attemptId = "11111111-1111-4111-8111-111111111111";
const params = { params: Promise.resolve({ attemptId }) };

describe("attempt page initial state", () => {
  beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

  it.each(["SUBMITTED", "AUTO_SUBMITTED", "INTERRUPTED", "ABANDONED"])("clears terminal %s draft before opening the result", async (status) => {
    sessionStorage.setItem(draftStorageKey(attemptId), "fictional unsaved response");
    vi.mocked(getExam).mockResolvedValue({ attempt: { attempt_id: attemptId, status, test_session_id: null } } as never);
    render(await AttemptShellPage(params));
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`/review/${attemptId}`));
    expect(sessionStorage.getItem(draftStorageKey(attemptId))).toBeNull();
  });

  it("returns a terminal Full Mock attempt to session advancement", async () => {
    const sessionId = "22222222-2222-4222-8222-222222222222";
    vi.mocked(getExam).mockResolvedValue({ attempt: { attempt_id: attemptId, status: "INTERRUPTED", test_session_id: sessionId } } as never);
    render(await AttemptShellPage(params));
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`/test-session/${sessionId}`));
  });

  it("does not convert backend failures to a missing page", async () => {
    vi.mocked(getExam).mockRejectedValue(new ApiError("API_ERROR", "backend unavailable", 500));
    await expect(AttemptShellPage(params)).rejects.toThrow("backend unavailable");
  });

  it("retains 404 handling for a missing attempt", async () => {
    vi.mocked(getExam).mockRejectedValue(new ApiError("NOT_FOUND", "missing", 404));
    await expect(AttemptShellPage(params)).rejects.toThrow("notFound");
  });
});
