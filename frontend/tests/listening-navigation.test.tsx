import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { recordNavigation, saveAnswer } from "@/lib/api/attempts";
import type { ExamPayload } from "@/lib/api/exam";
import { saveFlag } from "@/lib/api/exam";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, recordActivity: vi.fn(), recordNavigation: vi.fn(), saveAnswer: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
});

const attemptId = "22222222-2222-4222-8222-222222222222";
const part1 = "44444444-4444-4444-8444-444444444401";
const part2 = "44444444-4444-4444-8444-444444444402";
const q1 = "11111111-1111-4111-8111-111111111101";
const q2 = "11111111-1111-4111-8111-111111111102";
const q15 = "11111111-1111-4111-8111-111111111115";
const q25 = "11111111-1111-4111-8111-111111111125";
const q40 = "11111111-1111-4111-8111-111111111140";

function group(id: string, orderIndex: number, questions: Array<{ id: string; number: number; value: unknown; flagged: boolean }>) {
  return {
    id,
    question_type: "true_false_not_given",
    instruction: "",
    config: {},
    order_index: orderIndex,
    questions: questions.map((question, index) => ({
      ...question,
      prompt: `Statement ${question.number}`,
      config: {},
      order_index: index,
    })),
  };
}

function payload(): ExamPayload {
  const now = new Date().toISOString();
  return {
    attempt: {
      attempt_id: attemptId,
      test_version_id: "33333333-3333-4333-8333-333333333333",
      module: "LISTENING",
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
    test_title: "Listening navigation practice",
    passages: [],
    highlights: [],
    listening_audio_asset: null,
    writing_tasks: [],
    listening_parts: [
      {
        id: part2,
        title: "Section Two",
        order_index: 1,
        question_groups: [group("66666666-6666-4666-8666-666666666615", 0, [{ id: q15, number: 15, value: null, flagged: false }])],
      },
      {
        id: part1,
        title: "Section One",
        order_index: 0,
        question_groups: [
          group("66666666-6666-4666-8666-666666666612", 1, [{ id: q2, number: 2, value: null, flagged: false }]),
          group("66666666-6666-4666-8666-666666666611", 0, [{ id: q1, number: 1, value: "TRUE", flagged: false }]),
        ],
      },
      {
        id: "44444444-4444-4444-8444-444444444403",
        title: "Section Three",
        order_index: 2,
        question_groups: [group("66666666-6666-4666-8666-666666666625", 0, [{ id: q25, number: 25, value: null, flagged: true }])],
      },
      {
        id: "44444444-4444-4444-8444-444444444404",
        title: "Section Four",
        order_index: 3,
        question_groups: [group("66666666-6666-4666-8666-666666666640", 0, [{ id: q40, number: 40, value: null, flagged: false }])],
      },
    ],
  };
}

describe("Listening footer navigation", () => {
  const scrolled: Array<{ element: Element; options?: ScrollIntoViewOptions }> = [];
  let intersectionCallback: IntersectionObserverCallback = () => undefined;

  beforeEach(() => {
    vi.clearAllMocks();
    scrolled.length = 0;
    vi.mocked(saveAnswer).mockResolvedValue(undefined);
    vi.mocked(saveFlag).mockResolvedValue(undefined);
    vi.mocked(recordNavigation).mockResolvedValue(undefined);
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(function (this: Element, options?: ScrollIntoViewOptions) {
        scrolled.push({ element: this, options });
      }),
    });
    class MockIntersectionObserver {
      readonly root = null;
      readonly rootMargin = "0px";
      readonly thresholds = [0.35, 0.65];
      constructor(callback: IntersectionObserverCallback) { intersectionCallback = callback; }
      disconnect() {}
      observe() {}
      takeRecords(): IntersectionObserverEntry[] { return []; }
      unobserve() {}
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  });

  it("renders canonical global navigation in the footer and no in-content flag row", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const footer = view.container.querySelector(".listening-exam-footer")!;
    const sectionNavigation = within(footer as HTMLElement).getByRole("navigation", { name: "Section navigation" });
    const questionNavigation = within(footer as HTMLElement).getByRole("navigation", { name: "Question navigation" });

    expect(within(sectionNavigation).getAllByRole("button").map((button) => button.textContent)).toEqual(["Section 1", "Section 2", "Section 3", "Section 4"]);
    expect(within(questionNavigation).getAllByRole("button", { name: /Go to question/ }).map((button) => button.textContent)).toEqual(["1", "2", "15", "25", "40"]);
    expect(view.container.querySelectorAll(".exam-question-strip")).toHaveLength(1);
    expect(view.container.querySelector(".exam-flags")).not.toBeInTheDocument();
    expect(view.container.querySelector(".listening-question-pane")?.contains(questionNavigation)).toBe(false);
  });

  it("shows answered, unanswered, flagged, and current states", () => {
    const view = render(<ListeningRunner initial={payload()} />);

    expect(view.container.querySelector(`[data-nav-question-id="${q1}"]`)).toHaveClass("answered", "current");
    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("unanswered");
    expect(view.container.querySelector(`[data-nav-question-id="${q25}"]`)).toHaveClass("unanswered", "flagged");
  });

  it("navigates within the current Section and focuses the stable question target", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    scrolled.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));

    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;
    expect(scrolled.some((item) => item.element === target && item.options?.block === "center")).toBe(true);
    expect(target).toHaveFocus();
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
  });

  it("switches Section and completes pending navigation to the requested question", async () => {
    const view = render(<ListeningRunner initial={payload()} />);
    scrolled.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Go to question 15" }));

    expect(await screen.findByText("Section Two")).toBeInTheDocument();
    const target = await waitFor(() => {
      const element = view.container.querySelector(`.exam-question-target[data-question-id="${q15}"]`);
      expect(element).toBeInTheDocument();
      return element!;
    });
    await waitFor(() => expect(scrolled.some((item) => item.element === target)).toBe(true));
    expect(target).toHaveFocus();
    expect(screen.getByRole("button", { name: "Go to question 15" })).toHaveAttribute("aria-current", "true");
    await waitFor(() => expect(recordNavigation).toHaveBeenCalledWith(attemptId, "LISTENING_PART", part2));
    expect(recordNavigation).toHaveBeenCalledWith(attemptId, "QUESTION", q15);
  });

  it("updates the answered chip immediately and preserves answer autosave", async () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;

    fireEvent.click(within(target as HTMLElement).getByRole("radio", { name: "FALSE" }));

    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("answered", "current");
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q2, "FALSE"), { timeout: 1200 });
  });

  it("toggles a footer flag without navigating", async () => {
    const view = render(<ListeningRunner initial={payload()} />);

    fireEvent.click(screen.getByRole("button", { name: "Flag question 2" }));

    await waitFor(() => expect(saveFlag).toHaveBeenCalledWith(attemptId, q2, true));
    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("flagged");
    expect(screen.getByText("Section One")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to question 1" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Unflag question 2" })).toHaveAttribute("aria-pressed", "true");
  });

  it("tracks the current question from focus and auto-scrolls its footer chip", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    scrolled.length = 0;
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;

    fireEvent.focus(within(target as HTMLElement).getByRole("radio", { name: "TRUE" }));

    const chipButton = screen.getByRole("button", { name: "Go to question 2" });
    expect(chipButton).toHaveAttribute("aria-current", "true");
    expect(scrolled).toContainEqual({ element: chipButton, options: { block: "nearest", inline: "nearest" } });
  });

  it("tracks the most visible question with the Reading IntersectionObserver thresholds", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;

    act(() => intersectionCallback(
      [{ target, isIntersecting: true, intersectionRatio: 0.8 } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    ));

    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
  });

  it("manual Section navigation selects its first question and resets pane scroll", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const pane = view.container.querySelector(".listening-question-pane") as HTMLElement;
    pane.scrollTop = 240;

    fireEvent.click(screen.getByRole("button", { name: "Section 2" }));

    expect(screen.getByText("Section Two")).toBeInTheDocument();
    expect(pane.scrollTop).toBe(0);
    expect(screen.getByRole("button", { name: "Go to question 15" })).toHaveAttribute("aria-current", "true");
  });
});
