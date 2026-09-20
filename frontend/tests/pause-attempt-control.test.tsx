import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { pauseAttempt } from "@/lib/api/attempts";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, pauseAttempt: vi.fn() };
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
});
