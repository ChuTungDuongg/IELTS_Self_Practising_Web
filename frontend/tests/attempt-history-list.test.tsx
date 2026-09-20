import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { ApiError } from "@/lib/api/client";
import { deleteAttempt } from "@/lib/api/attempts";
import type { HistoryGroup, HistoryItem, HistoryResponse } from "@/lib/api/history";

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
  test_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  test_version_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  test_title: "Fictional submitted attempt",
  version_number: 1,
  module: "READING",
  status: "SUBMITTED",
  started_at: "2026-09-20T00:00:00Z",
  finished_at: "2026-09-20T00:01:00Z",
  elapsed_seconds: 60,
  raw_score: 35,
  max_score: 40,
  band_score: 8.0,
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
  band_score: null,
};

const listening: HistoryItem = {
  ...submitted,
  attempt_id: "33333333-3333-4333-8333-333333333333",
  test_title: "Fictional submitted attempt",
  module: "LISTENING",
  raw_score: 37,
  band_score: 8.5,
};

const writing: HistoryItem = {
  ...submitted,
  attempt_id: "44444444-4444-4444-8444-444444444444",
  test_title: "Fictional submitted attempt",
  module: "WRITING",
  raw_score: null,
  max_score: null,
  band_score: 7.0,
};

const completeGroup: HistoryGroup = {
  test_id: submitted.test_id,
  test_version_id: submitted.test_version_id,
  test_title: "Fictional submitted attempt",
  version_number: 1,
  reading: submitted,
  listening,
  writing,
  overall_band_score: 8.0,
};

function history(items: HistoryItem[], groups: HistoryGroup[] = []): HistoryResponse {
  return { items, groups, total: items.length };
}

describe("AttemptHistoryList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(["IN_PROGRESS", "SUBMITTED", "INTERRUPTED", "AUTO_SUBMITTED", "ABANDONED"] as const)(
    "renders Delete for %s attempts",
    (status) => {
      render(<AttemptHistoryList initialHistory={history([{ ...submitted, status }])} />);

      expect(
        screen.getByRole("button", { name: "Delete Fictional submitted attempt" }),
      ).toBeInTheDocument();
    },
  );

  it("keeps the primary attempt action ahead of the quiet destructive action", () => {
    render(<AttemptHistoryList initialHistory={history([inProgress])} />);

    expect(screen.getByRole("link", { name: "Continue" })).toHaveClass("btn", "btn-primary");
    expect(screen.getByRole("button", { name: "Delete Fictional active attempt" })).toHaveClass(
      "btn-danger-ghost",
    );
  });

  it("renders the shared empty state when there are no attempts", () => {
    const { container } = render(<AttemptHistoryList initialHistory={history([])} />);

    expect(screen.getByRole("heading", { name: "No practice attempts yet" })).toBeInTheDocument();
    expect(container.querySelector(".empty-state")).toBeInTheDocument();
  });

  it("opens the confirmation dialog and cancellation sends no request", () => {
    render(<AttemptHistoryList initialHistory={history([inProgress])} />);

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
    render(<AttemptHistoryList initialHistory={history([submitted, inProgress])} />);

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
    render(<AttemptHistoryList initialHistory={history([submitted])} />);

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
    render(<AttemptHistoryList initialHistory={history([submitted])} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional submitted attempt" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete attempt" }));

    expect(await screen.findByRole("heading", { name: "No practice attempts yet" })).toBeInTheDocument();
  });

  it("shows every attempt by skill with backend score availability copy", () => {
    const shortObjective = {
      ...submitted,
      attempt_id: "55555555-5555-4555-8555-555555555555",
      test_title: "Short objective set",
      raw_score: 18,
      max_score: 20,
      band_score: null,
    };
    const ungradedWriting = {
      ...writing,
      attempt_id: "66666666-6666-4666-8666-666666666666",
      test_title: "Ungraded Writing",
      band_score: null,
    };
    render(<AttemptHistoryList initialHistory={history([submitted, shortObjective, ungradedWriting, inProgress])} />);

    expect(screen.getByRole("tab", { name: "By skill" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Band 8.0")).toBeInTheDocument();
    expect(screen.getByText("Raw 35 / 40")).toBeInTheDocument();
    expect(screen.getByText("Official band unavailable")).toBeInTheDocument();
    expect(screen.getByText("Not graded")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", `/attempt/${inProgress.attempt_id}`);
  });

  it("renders backend-produced exact-version groups and does not derive incomplete overall", () => {
    const incomplete: HistoryGroup = {
      ...completeGroup,
      test_version_id: "77777777-7777-4777-8777-777777777777",
      version_number: 2,
      listening: null,
      writing: null,
      overall_band_score: null,
    };
    render(<AttemptHistoryList initialHistory={history([submitted, listening, writing], [completeGroup, incomplete])} />);

    fireEvent.click(screen.getByRole("tab", { name: "By test" }));
    expect(screen.getByText("Overall band 8.0")).toBeInTheDocument();
    expect(screen.getByText("Overall band —")).toBeInTheDocument();
    expect(screen.getByText("Version 1")).toBeInTheDocument();
    expect(screen.getByText("Version 2")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Review Reading" })[0]).toHaveAttribute(
      "href",
      `/review/${submitted.attempt_id}`,
    );
    expect(screen.getByRole("link", { name: "Review Listening" })).toHaveAttribute(
      "href",
      `/review/${listening.attempt_id}`,
    );
    expect(screen.getByRole("link", { name: "Review Writing" })).toHaveAttribute(
      "href",
      `/review/${writing.attempt_id}`,
    );
  });
});
