import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { ApiError } from "@/lib/api/client";
import { deleteAttempt } from "@/lib/api/attempts";
import type { HistoryItem } from "@/lib/api/history";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, deleteAttempt: vi.fn() };
});

const submitted: HistoryItem = {
  attempt_id: "11111111-1111-4111-8111-111111111111",
  test_title: "Fictional submitted attempt",
  version_number: 1,
  module: "READING",
  status: "SUBMITTED",
  started_at: "2026-09-20T00:00:00Z",
  finished_at: "2026-09-20T00:01:00Z",
  elapsed_seconds: 60,
  raw_score: 1,
  max_score: 1,
};

const inProgress: HistoryItem = {
  ...submitted,
  attempt_id: "22222222-2222-4222-8222-222222222222",
  test_title: "Fictional active attempt",
  status: "IN_PROGRESS",
  finished_at: null,
  elapsed_seconds: null,
  raw_score: null,
  max_score: null,
};

describe("AttemptHistoryList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(["IN_PROGRESS", "SUBMITTED", "INTERRUPTED", "AUTO_SUBMITTED", "ABANDONED"])(
    "renders Delete for %s attempts",
    (status) => {
      render(<AttemptHistoryList initialItems={[{ ...submitted, status }]} />);

      expect(
        screen.getByRole("button", { name: "Delete Fictional submitted attempt" }),
      ).toBeInTheDocument();
    },
  );

  it("keeps the primary attempt action ahead of the quiet destructive action", () => {
    render(<AttemptHistoryList initialItems={[inProgress]} />);

    expect(screen.getByRole("link", { name: "Continue" })).toHaveClass("btn", "btn-primary");
    expect(screen.getByRole("button", { name: "Delete Fictional active attempt" })).toHaveClass(
      "btn-danger-ghost",
    );
  });

  it("renders the shared empty state when there are no attempts", () => {
    const { container } = render(<AttemptHistoryList initialItems={[]} />);

    expect(screen.getByRole("heading", { name: "No practice attempts yet" })).toBeInTheDocument();
    expect(container.querySelector(".empty-state")).toBeInTheDocument();
  });

  it("opens the confirmation dialog and cancellation sends no request", () => {
    render(<AttemptHistoryList initialItems={[inProgress]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional active attempt" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Delete this attempt?");
    expect(dialog).toHaveTextContent("This attempt is still in progress.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(deleteAttempt).not.toHaveBeenCalled();
    expect(screen.getByText("Fictional active attempt")).toBeInTheDocument();
  });

  it("confirms once with the selected attempt and removes it immediately", async () => {
    let resolveDelete: (() => void) | undefined;
    vi.mocked(deleteAttempt).mockReturnValue(
      new Promise<void>((resolve) => {
        resolveDelete = resolve;
      }),
    );
    render(<AttemptHistoryList initialItems={[submitted, inProgress]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional submitted attempt" }));
    const confirm = screen.getByRole("button", { name: "Delete attempt" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(deleteAttempt).toHaveBeenCalledTimes(1);
    expect(deleteAttempt).toHaveBeenCalledWith(submitted.attempt_id);
    expect(confirm).toBeDisabled();
    resolveDelete?.();

    await waitFor(() =>
      expect(screen.queryByText("Fictional submitted attempt")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Fictional active attempt")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("keeps the row and shows a retryable error when deletion fails", async () => {
    vi.mocked(deleteAttempt).mockRejectedValue(
      new ApiError("DELETE_FAILED", "The attempt could not be deleted.", 500),
    );
    render(<AttemptHistoryList initialItems={[submitted]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional submitted attempt" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete attempt" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The attempt could not be deleted.",
    );
    expect(screen.getByText("Fictional submitted attempt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete attempt" })).toBeEnabled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows the existing empty state after deleting the final row", async () => {
    vi.mocked(deleteAttempt).mockResolvedValue(undefined);
    render(<AttemptHistoryList initialItems={[submitted]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional submitted attempt" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete attempt" }));

    expect(await screen.findByRole("heading", { name: "No practice attempts yet" })).toBeInTheDocument();
  });
});
