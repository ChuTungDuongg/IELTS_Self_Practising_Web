import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { ApiError } from "@/lib/api/client";
import { deleteAttempt, resumeAttempt } from "@/lib/api/attempts";
import { deleteTestSession } from "@/lib/api/test-sessions";
import type { HistoryGroup, HistoryItem, HistoryResponse, MockHistoryGroup } from "@/lib/api/history";

const refresh = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push }),
}));

vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, deleteAttempt: vi.fn(), resumeAttempt: vi.fn() };
});
vi.mock("@/lib/api/test-sessions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/test-sessions")>();
  return { ...actual, deleteTestSession: vi.fn() };
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
  timer_mode: "COUNT_UP",
  timer_limit_seconds: null,
  remaining_seconds: null,
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

const paused: HistoryItem = {
  ...inProgress,
  attempt_id: "88888888-8888-4888-8888-888888888888",
  test_title: "Fictional paused attempt",
  status: "PAUSED",
  timer_mode: "COUNTDOWN",
  timer_limit_seconds: 3600,
  elapsed_seconds: 600,
  remaining_seconds: 3000,
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

const activeSession: MockHistoryGroup = {
  session_id: "99999999-9999-4999-8999-999999999999",
  test_version_id: submitted.test_version_id,
  test_title: "Cambridge 11 Test 2",
  version_number: 4,
  status: "IN_PROGRESS",
  started_at: "2026-09-20T00:00:00Z",
  finished_at: null,
  listening: null,
  reading: null,
  writing: null,
  overall_band_score: null,
};

function history(items: HistoryItem[], groups: HistoryGroup[] = [], sessions: MockHistoryGroup[] = []): HistoryResponse {
  return { items, groups, sessions, total: items.length };
}

describe("AttemptHistoryList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each(["IN_PROGRESS", "PAUSED", "SUBMITTED", "INTERRUPTED", "AUTO_SUBMITTED", "ABANDONED"] as const)(
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

  it("groups an active Full Mock header, skills, and Resume action into one card", () => {
    const { container } = render(<AttemptHistoryList initialHistory={history([inProgress], [], [activeSession])} />);
    const section = container.querySelector(".history-session-section")!;
    const card = section.querySelector(".history-session-card")!;

    expect(within(section as HTMLElement).getByRole("heading", { name: "Full Mock sessions" })).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("Full Mock")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("Cambridge 11 Test 2")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("Version 4")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("In progress")).toBeInTheDocument();
    const skills = card.querySelector(".history-group-skills")!;
    expect(within(skills as HTMLElement).getByText("Listening")).toBeInTheDocument();
    expect(within(skills as HTMLElement).getByText("Reading")).toBeInTheDocument();
    expect(within(skills as HTMLElement).getByText("Writing")).toBeInTheDocument();
    expect(within(skills as HTMLElement).getAllByText("No finalized attempt")).toHaveLength(3);
    expect(within(card.querySelector(".history-group-footer") as HTMLElement).getByRole("link", { name: "Resume Full Mock" }))
      .toHaveAttribute("href", `/test-session/${activeSession.session_id}`);
    expect(screen.getByRole("tab", { name: "By skill" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", `/attempt/${inProgress.attempt_id}`);
    expect(screen.getByRole("button", { name: "Delete Fictional active attempt" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "By test" }));
    expect(screen.getByRole("tab", { name: "By test" })).toHaveAttribute("aria-selected", "true");
    expect(card).toBeInTheDocument();
  });

  it("shows completed Full Mock results without an empty Resume footer", () => {
    const { container } = render(<AttemptHistoryList initialHistory={history(
      [submitted, listening, writing],
      [],
      [{ ...activeSession, status: "COMPLETED", finished_at: "2026-09-20T01:00:00Z", reading: submitted, listening, writing, overall_band_score: 8.0 }],
    )} />);
    const card = container.querySelector(".history-session-card")!;
    expect(within(card as HTMLElement).getByText("Overall band 8.0")).toBeInTheDocument();
    expect(within(card.querySelector(".history-group-footer") as HTMLElement).getByRole("button", { name: "Delete Full Mock" })).toBeInTheDocument();
    expect(within(card as HTMLElement).queryByRole("link", { name: "Resume Full Mock" })).not.toBeInTheDocument();
    expect(within(card as HTMLElement).getByRole("link", { name: "Review Listening" })).toBeInTheDocument();
    expect(within(card as HTMLElement).getByRole("link", { name: "Review Reading" })).toBeInTheDocument();
    expect(within(card as HTMLElement).getByRole("link", { name: "Review Writing" })).toBeInTheDocument();
  });

  it("confirms Full Mock deletion and removes its session, child rows, and test group without F5", async () => {
    vi.mocked(deleteTestSession).mockResolvedValue(undefined);
    const child = { ...submitted, test_session_id: activeSession.session_id };
    const group = { ...completeGroup, reading: child, listening: null, writing: null };
    render(<AttemptHistoryList initialHistory={history([child, paused], [group], [activeSession])} />);

    const card = screen.getByText("Cambridge 11 Test 2").closest(".history-session-card")!;
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: "Delete Full Mock" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Delete this Full Mock?");
    expect(dialog).toHaveTextContent("Listening, Reading and Writing attempts");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(deleteTestSession).not.toHaveBeenCalled();
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: "Delete Full Mock" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete Full Mock" }));

    await waitFor(() => expect(deleteTestSession).toHaveBeenCalledWith(activeSession.session_id));
    expect(screen.queryByText("Cambridge 11 Test 2")).not.toBeInTheDocument();
    expect(screen.queryByText("Fictional submitted attempt")).not.toBeInTheDocument();
    expect(screen.getByText("Fictional paused attempt")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "By test" }));
    expect(screen.getByRole("heading", { name: "No finalized test groups yet" })).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledOnce();
    expect(deleteAttempt).not.toHaveBeenCalled();
  });

  it("hides standalone Delete for Full Mock children but keeps it for standalone attempts", () => {
    render(<AttemptHistoryList initialHistory={history([
      { ...submitted, test_session_id: activeSession.session_id },
      paused,
    ], [], [activeSession])} />);
    expect(screen.queryByRole("button", { name: "Delete Fictional submitted attempt" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete Fictional paused attempt" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete Full Mock" })).toBeInTheDocument();
  });

  it("retains ungraded Writing and its review link in a completed Full Mock and By test", () => {
    const childWriting = { ...writing, band_score: null, test_session_id: activeSession.session_id };
    const childReading = { ...submitted, test_session_id: activeSession.session_id };
    const childListening = { ...listening, test_session_id: activeSession.session_id };
    render(<AttemptHistoryList initialHistory={history(
      [childWriting, childReading, childListening],
      [{ ...completeGroup, reading: childReading, listening: childListening, writing: childWriting, overall_band_score: null }],
      [{ ...activeSession, status: "COMPLETED", finished_at: "2026-09-20T01:00:00Z", reading: childReading, listening: childListening, writing: childWriting }],
    )} />);
    const card = screen.getByText("Cambridge 11 Test 2").closest(".history-session-card")!;
    expect(within(card as HTMLElement).getByText("Not graded")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByRole("link", { name: "Review Writing" })).toHaveAttribute("href", `/review/${writing.attempt_id}`);
    fireEvent.click(screen.getByRole("tab", { name: "By test" }));
    expect(screen.getAllByText("Overall band —")).toHaveLength(2);
    expect(screen.getAllByText("Not graded")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Review Writing" })).toHaveLength(2);
  });

  it("resumes a paused row through the backend before navigating", async () => {
    vi.mocked(resumeAttempt).mockResolvedValue({} as never);
    render(<AttemptHistoryList initialHistory={history([paused])} />);

    expect(screen.getByText("Remaining: 50:00")).toBeInTheDocument();
    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));

    await waitFor(() => expect(resumeAttempt).toHaveBeenCalledWith(paused.attempt_id));
    expect(push).toHaveBeenCalledWith(`/attempt/${paused.attempt_id}`);
  });

  it("keeps a paused row in History when resume fails", async () => {
    vi.mocked(resumeAttempt).mockRejectedValue(new ApiError("RESUME_FAILED", "Resume failed.", 409));
    render(<AttemptHistoryList initialHistory={history([paused])} />);
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Resume failed.");
    expect(screen.getByText("Fictional paused attempt")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
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
    expect(dialog).toHaveTextContent("This attempt is not finalized.");
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
    const readingScore = screen.getByTestId(`history-score-${submitted.attempt_id}`);
    expect(within(readingScore).getByText("Band")).toHaveClass("history-band-label");
    expect(within(readingScore).getByText("8.0")).toHaveClass("history-band-value");
    expect(within(readingScore).getByText("35 / 40 correct")).toBeInTheDocument();
    expect(screen.getByText("Official band unavailable")).toBeInTheDocument();
    expect(screen.getByText("Not graded")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", `/attempt/${inProgress.attempt_id}`);
  });

  it("shows finalized Writing prominently without inventing scores for active attempts", () => {
    render(<AttemptHistoryList initialHistory={history([writing, inProgress, paused])} />);

    const writingScore = screen.getByTestId(`history-score-${writing.attempt_id}`);
    expect(within(writingScore).getByText("Band")).toBeInTheDocument();
    expect(within(writingScore).getByText("7.0")).toHaveClass("history-band-value");
    expect(screen.getByTestId(`history-score-${inProgress.attempt_id}`)).toHaveTextContent("In progress");
    expect(screen.getByTestId(`history-score-${paused.attempt_id}`)).toHaveTextContent("Paused");
    expect(screen.getAllByText("Band")).toHaveLength(1);
  });

  it("renders dates deterministically in the project timezone", () => {
    render(<AttemptHistoryList initialHistory={history([{ ...submitted, started_at: "2026-09-20T15:00:01Z" }])} />);
    expect(screen.getByText("Started 20/09/2026, 22:00:01")).toBeInTheDocument();
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

  it("replaces group selection and overall when refreshed server props arrive", () => {
    const { rerender } = render(
      <AttemptHistoryList
        initialHistory={history([submitted, listening, writing], [completeGroup])}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "By test" }));
    expect(screen.getByText("Overall band 8.0")).toBeInTheDocument();

    rerender(
      <AttemptHistoryList
        initialHistory={history([submitted, listening], [{
          ...completeGroup,
          writing: null,
          overall_band_score: null,
        }])}
      />,
    );

    expect(screen.getByText("Overall band —")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review Writing" })).not.toBeInTheDocument();
  });
});
