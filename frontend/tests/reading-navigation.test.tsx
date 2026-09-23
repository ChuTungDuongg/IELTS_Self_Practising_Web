import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { getAttempt, recordActivity, saveAnswer } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import type { ExamPayload } from "@/lib/api/exam";
import { saveFlag, submitAttempt } from "@/lib/api/exam";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, getAttempt: vi.fn(), recordActivity: vi.fn(), saveAnswer: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, createHighlight: vi.fn(), deleteAllHighlights: vi.fn(), deleteHighlight: vi.fn(), getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
});

const q1 = "11111111-1111-4111-8111-111111111101";
const q2 = "11111111-1111-4111-8111-111111111102";
const q19 = "11111111-1111-4111-8111-111111111119";

function group(id: string, orderIndex: number, questions: Array<{ id: string; number: number; value: unknown; flagged: boolean }>) {
  return {
    id,
    question_type: "true_false_not_given",
    instruction: "",
    config: {},
    order_index: orderIndex,
    questions: questions.map((question, index) => ({ ...question, prompt: `Statement ${question.number}`, config: {}, order_index: index })),
  };
}

function payload(): ExamPayload {
  const now = new Date().toISOString();
  return {
    attempt: {
      attempt_id: "22222222-2222-4222-8222-222222222222",
      test_version_id: "33333333-3333-4333-8333-333333333333",
      module: "READING",
      status: "IN_PROGRESS",
      finished_reason: null,
      timer_mode: "COUNT_UP",
      timer_limit_seconds: null,
      started_at: now,
      paused_at: null,
      total_paused_seconds: 0,
      deadline_at: null,
      last_active_at: now,
      finished_at: null,
      elapsed_seconds: 0,
      remaining_seconds: null,
      raw_score: null,
      max_score: null,
      band_score: null,
      server_time: now,
    },
    test_title: "Navigation practice",
    highlights: [],
    listening_audio_asset: null,
    listening_parts: [],
    writing_tasks: [],
    passages: [
      {
        id: "44444444-4444-4444-8444-444444444402",
        title: "Passage Two",
        order_index: 1,
        blocks: [{ id: "55555555-5555-4555-8555-555555555502", type: "paragraph", label: "A", text: "Second fictional passage." }],
        question_groups: [group("66666666-6666-4666-8666-666666666602", 0, [{ id: q19, number: 19, value: null, flagged: true }])],
      },
      {
        id: "44444444-4444-4444-8444-444444444401",
        title: "Passage One",
        order_index: 0,
        blocks: [{ id: "55555555-5555-4555-8555-555555555501", type: "paragraph", label: "A", text: "First fictional passage." }],
        question_groups: [
          group("66666666-6666-4666-8666-666666666612", 1, [{ id: q2, number: 2, value: null, flagged: false }]),
          group("66666666-6666-4666-8666-666666666611", 0, [{ id: q1, number: 1, value: "TRUE", flagged: false }]),
        ],
      },
    ],
  };
}

describe("Reading footer navigation", () => {
  const scrolledElements: Element[] = [];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(saveAnswer).mockResolvedValue(undefined);
    scrolledElements.length = 0;
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(function (this: Element) { scrolledElements.push(this); }),
    });
  });

  it("renders canonical passage and question rows without per-group flag controls", () => {
    const view = render(<ReadingRunner initial={payload()} />);
    expect(screen.getByRole("button", { name: "Pause & exit" })).toBeInTheDocument();
    expect(view.container.querySelector(".exam-passage")).toBeInTheDocument();
    expect(view.container.querySelector(".exam-passage-body")).toBeInTheDocument();
    expect(view.container.querySelector(".exam-question-panel-heading")).toBeInTheDocument();
    const footer = view.container.querySelector(".reading-exam-footer")!;
    const passageRow = footer.querySelector(".exam-passage-navigation")!;
    const questionStrip = footer.querySelector(".exam-question-strip")!;

    expect(within(passageRow as HTMLElement).getAllByRole("button").map((button) => button.textContent)).toEqual(["Passage 1", "Passage 2"]);
    expect(within(questionStrip as HTMLElement).getAllByRole("button", { name: /Go to question/ }).map((button) => button.textContent)).toEqual(["1", "2", "19"]);
    expect(view.container.querySelectorAll(".exam-question-strip")).toHaveLength(1);
    expect(view.container.querySelector(".exam-flags")).not.toBeInTheDocument();
    expect(footer.firstElementChild as HTMLElement).toContainElement(passageRow as HTMLElement);
    expect(passageRow.nextElementSibling).toBe(questionStrip);
  });

  it("shows answered, unanswered, flagged and current question states", () => {
    const view = render(<ReadingRunner initial={payload()} />);
    const chip1 = view.container.querySelector(`[data-nav-question-id="${q1}"]`)!;
    const chip2 = view.container.querySelector(`[data-nav-question-id="${q2}"]`)!;
    const chip19 = view.container.querySelector(`[data-nav-question-id="${q19}"]`)!;

    expect(chip1).toHaveClass("answered", "current");
    expect(chip2).toHaveClass("unanswered");
    expect(chip19).toHaveClass("unanswered", "flagged");
  });

  it("switches passage and scrolls to the stable UUID target", async () => {
    const view = render(<ReadingRunner initial={payload()} />);
    scrolledElements.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Go to question 19" }));

    expect(await screen.findByText("Passage Two")).toBeInTheDocument();
    const target = await waitFor(() => {
      const element = view.container.querySelector(`.exam-question-target[data-question-id="${q19}"]`);
      expect(element).toBeInTheDocument();
      return element!;
    });
    await waitFor(() => expect(scrolledElements).toContain(target));
    expect(target.id).toBe(`question-${q19}`);
    expect(target).toHaveClass("is-navigation-target");
    expect(document.activeElement).toBe(target);
  });

  it("toggles a footer flag without navigating", async () => {
    render(<ReadingRunner initial={payload()} />);

    fireEvent.click(screen.getByRole("button", { name: "Flag question 2" }));

    await waitFor(() => expect(saveFlag).toHaveBeenCalledWith("22222222-2222-4222-8222-222222222222", q2, true));
    expect(screen.getByText("Passage One")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unflag question 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to question 1" })).toHaveAttribute("aria-current", "true");
  });

  it("keeps submission available after the navigation refactor", async () => {
    render(<ReadingRunner initial={payload()} />);

    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));

    await waitFor(() => expect(submitAttempt).toHaveBeenCalledWith("22222222-2222-4222-8222-222222222222"));
    expect(push).toHaveBeenCalledWith("/review/22222222-2222-4222-8222-222222222222");
  });

  it("keeps answer autosave and timer display working", async () => {
    const view = render(<ReadingRunner initial={payload()} />);

    expect(screen.getByText(/Time used 00:00/)).toBeInTheDocument();
    const question = view.container.querySelector(`[data-question-id="${q1}"]`)!;
    fireEvent.click(within(question as HTMLElement).getByRole("radio", { name: "FALSE" }));

    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith("22222222-2222-4222-8222-222222222222", q1, "FALSE"), { timeout: 1200 });
  });

  it("reconciles a finalized autosave and stops further answer writes", async () => {
    const initial = payload();
    vi.mocked(saveAnswer).mockRejectedValueOnce(new ApiError("ATTEMPT_FINALIZED", "finalized", 409));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "INTERRUPTED" });
    const view = render(<ReadingRunner initial={initial} />);
    const question = view.container.querySelector(`[data-question-id="${q1}"]`)!;
    fireEvent.click(within(question as HTMLElement).getByRole("radio", { name: "FALSE" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${initial.attempt.attempt_id}`), { timeout: 1500 });
    expect(getAttempt).toHaveBeenCalledWith(initial.attempt.attempt_id);
    expect(screen.getByRole("status")).toHaveTextContent("Attempt finished");
    expect(screen.queryByText("Save failed")).not.toBeInTheDocument();
    expect(saveAnswer).toHaveBeenCalledTimes(1);
  });

  it("stops heartbeat after the backend finalizes the attempt", async () => {
    const initial = payload();
    vi.mocked(recordActivity).mockRejectedValueOnce(new ApiError("ATTEMPT_FINALIZED", "finalized", 409));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "INTERRUPTED" });
    render(<ReadingRunner initial={initial} />);
    fireEvent.click(window);
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${initial.attempt.attempt_id}`));
    fireEvent.click(window);
    expect(recordActivity).toHaveBeenCalledTimes(1);
  });
});
