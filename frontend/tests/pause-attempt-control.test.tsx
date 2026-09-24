import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { getAttempt, pauseAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, getAttempt: vi.fn(), pauseAttempt: vi.fn() };
});

const attemptId = "11111111-1111-4111-8111-111111111111";

describe("PauseAttemptControl", () => {
  beforeEach(() => vi.clearAllMocks());

  it("confirms, flushes pending work, pauses, then exits to History", async () => {
    const beforePause = vi.fn().mockResolvedValue(undefined);
    vi.mocked(pauseAttempt).mockResolvedValue({ status: "PAUSED" } as never);
    render(<PauseAttemptControl attemptId={attemptId} beforePause={beforePause} />);

    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Your progress will be saved");
    fireEvent.click(within(dialog).getByRole("button", { name: "Pause & exit" }));

    await waitFor(() => expect(pauseAttempt).toHaveBeenCalledWith(attemptId));
    expect(beforePause).toHaveBeenCalledTimes(1);
    expect(beforePause.mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(pauseAttempt).mock.invocationCallOrder[0]);
    expect(push).toHaveBeenCalledWith("/history");
  });

  it("stays on the runner and shows an error when pausing fails", async () => {
    vi.mocked(pauseAttempt).mockRejectedValue(new Error("offline"));
    render(<PauseAttemptControl attemptId={attemptId} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be saved and paused");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("waits for beforePause and blocks duplicate Pause requests", async () => {
    let release!: () => void;
    const pendingSave = new Promise<void>((resolve) => { release = resolve; });
    const beforePause = vi.fn(() => pendingSave);
    vi.mocked(pauseAttempt).mockResolvedValue({ attempt_id: attemptId, status: "PAUSED" } as never);
    render(<PauseAttemptControl attemptId={attemptId} beforePause={beforePause} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" });
    fireEvent.click(confirm);
    expect(pauseAttempt).not.toHaveBeenCalled();
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(beforePause).toHaveBeenCalledTimes(1);
    release();
    await waitFor(() => expect(pauseAttempt).toHaveBeenCalledTimes(1));
  });

  it("does not pause when the latest answer cannot be flushed", async () => {
    const beforePause = vi.fn().mockRejectedValue(new Error("save failed"));
    render(<PauseAttemptControl attemptId={attemptId} beforePause={beforePause} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be saved and paused");
    expect(pauseAttempt).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("reconciles a finalized beforePause write without sending a second pause", async () => {
    const beforePause = vi.fn().mockRejectedValue(new ApiError("ATTEMPT_FINALIZED", "finalized", 409));
    vi.mocked(getAttempt).mockResolvedValue({ attempt_id: attemptId, status: "INTERRUPTED" } as never);
    render(<PauseAttemptControl attemptId={attemptId} beforePause={beforePause} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${attemptId}`));
    expect(pauseAttempt).not.toHaveBeenCalled();
  });

  it.each(["INTERRUPTED", "AUTO_SUBMITTED", "SUBMITTED", "ABANDONED"])("routes %s returned by pause", async (status) => {
    vi.mocked(pauseAttempt).mockResolvedValue({ attempt_id: attemptId, status } as never);
    render(<PauseAttemptControl attemptId={attemptId} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${attemptId}`));
  });

  it("routes a finalized Full Mock back through session advancement", async () => {
    const sessionId = "22222222-2222-4222-8222-222222222222";
    vi.mocked(pauseAttempt).mockResolvedValue({ attempt_id: attemptId, status: "AUTO_SUBMITTED", test_session_id: sessionId } as never);
    render(<PauseAttemptControl attemptId={attemptId} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/test-session/${sessionId}`));
  });
});
