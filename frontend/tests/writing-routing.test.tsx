import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AttemptShellPage from "@/app/attempt/[attemptId]/page";
import ReviewShellPage from "@/app/review/[attemptId]/page";
import { StartAttempt } from "@/features/exam/start-attempt";
import { resumeAttempt, startAttempt } from "@/lib/api/attempts";
import { getExam, getWritingReview } from "@/lib/api/exam";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push, refresh: vi.fn() }),
}));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, startAttempt: vi.fn(), resumeAttempt: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, getExam: vi.fn(), getWritingReview: vi.fn() };
});
vi.mock("@/features/writing/writing-runner", () => ({
  WritingRunner: () => <p>Writing runner selected</p>,
}));
vi.mock("@/features/writing/writing-review", () => ({
  WritingReviewView: () => <p>Writing review selected</p>,
}));

const attemptId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";

describe("Writing routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts Writing with the 60-minute default", async () => {
    vi.mocked(startAttempt).mockResolvedValue({ attempt_id: attemptId } as never);
    render(<StartAttempt versionId={versionId} module="WRITING" />);

    expect(screen.getByLabelText("Practice timer")).toHaveValue("3600");
    fireEvent.click(screen.getByRole("button", { name: "Start Writing" }));

    await waitFor(() => expect(startAttempt).toHaveBeenCalledWith({
      test_version_id: versionId,
      module: "WRITING",
      timer: { mode: "COUNTDOWN", duration_seconds: 3600 },
    }));
    expect(push).toHaveBeenCalledWith(`/attempt/${attemptId}`);
  });

  it("routes Writing attempts to the Writing runner", async () => {
    vi.mocked(getExam).mockResolvedValue({ attempt: { module: "WRITING" } } as never);
    render(await AttemptShellPage({ params: Promise.resolve({ attemptId }) }));
    expect(screen.getByText("Writing runner selected")).toBeInTheDocument();
  });

  it("gates a paused attempt until it is resumed", async () => {
    const now = "2026-09-20T00:00:00Z";
    vi.mocked(getExam).mockResolvedValue({
      test_title: "Paused fictional test",
      attempt: {
        attempt_id: attemptId, test_version_id: versionId, module: "WRITING", status: "PAUSED",
        finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null,
        started_at: now, paused_at: now, total_paused_seconds: 30, deadline_at: null,
        last_active_at: now, finished_at: null, elapsed_seconds: 125, remaining_seconds: null,
        raw_score: null, max_score: null, band_score: null, server_time: now,
      },
    } as never);
    vi.mocked(resumeAttempt).mockResolvedValue({} as never);

    render(await AttemptShellPage({ params: Promise.resolve({ attemptId }) }));
    expect(screen.getByRole("heading", { name: "Attempt paused" })).toBeInTheDocument();
    expect(screen.getByText("Practice time: 02:05")).toBeInTheDocument();
    expect(screen.queryByText("Writing runner selected")).not.toBeInTheDocument();
    expect(resumeAttempt).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Resume attempt" }));
    await waitFor(() => expect(resumeAttempt).toHaveBeenCalledWith(attemptId));
  });

  it("loads the Writing-specific review before rendering", async () => {
    vi.mocked(getExam).mockResolvedValue({ attempt: { module: "WRITING" } } as never);
    vi.mocked(getWritingReview).mockResolvedValue({ tasks: [] } as never);
    render(await ReviewShellPage({ params: Promise.resolve({ attemptId }) }));
    expect(getWritingReview).toHaveBeenCalledWith(attemptId);
    expect(screen.getByText("Writing review selected")).toBeInTheDocument();
  });
});
