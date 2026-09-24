import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { getAttempt, recordActivity, recordNavigation, saveAnswer } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import type { ExamPayload } from "@/lib/api/exam";
import { saveFlag, submitAttempt } from "@/lib/api/exam";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, getAttempt: vi.fn(), recordActivity: vi.fn(), recordNavigation: vi.fn(), saveAnswer: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, createHighlight: vi.fn(), deleteAllHighlights: vi.fn(), deleteHighlight: vi.fn(), getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
});

const q1 = "11111111-1111-4111-8111-111111111101";
const q2 = "11111111-1111-4111-8111-111111111102";
const q19 = "11111111-1111-4111-8111-111111111119";

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

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
  const scrolls: Array<{ element: HTMLElement; options: ScrollToOptions }> = [];
  let intersectionCallback: IntersectionObserverCallback = () => undefined;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getAttempt).mockReset();
    vi.mocked(submitAttempt).mockReset();
    vi.mocked(saveAnswer).mockResolvedValue(undefined);
    vi.mocked(recordNavigation).mockResolvedValue(undefined);
    scrolls.length = 0;
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(function (this: HTMLElement, options: ScrollToOptions) {
        scrolls.push({ element: this, options });
        if (options.top !== undefined) this.scrollTop = options.top;
        if (options.left !== undefined) this.scrollLeft = options.left;
      }),
    });
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
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

  afterEach(() => vi.useRealTimers());

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
    scrolls.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Go to question 19" }));

    expect(await screen.findByText("Passage Two")).toBeInTheDocument();
    const target = await waitFor(() => {
      const element = view.container.querySelector(`.exam-question-target[data-question-id="${q19}"]`);
      expect(element).toBeInTheDocument();
      return element!;
    });
    const pane = view.container.querySelector(".exam-questions")!;
    await waitFor(() => expect(scrolls.some((item) => item.element === pane && item.options.top !== undefined)).toBe(true));
    expect(target.id).toBe(`question-${q19}`);
    expect(target).toHaveClass("is-navigation-target");
    expect(screen.getByRole("button", { name: "Go to question 19" })).toHaveAttribute("aria-current", "true");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("scrolls the local pane within a passage and ignores an intermediate observer result", () => {
    const view = render(<ReadingRunner initial={payload()} />);
    scrolls.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));
    expect(scrolls.some((item) => item.element === view.container.querySelector(".exam-questions"))).toBe(true);
    const first = view.container.querySelector(`.exam-question-target[data-question-id="${q1}"]`)!;
    act(() => intersectionCallback([{ target: first, isIntersecting: true, intersectionRatio: 0.9 } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(vi.mocked(recordNavigation).mock.calls.filter((call) => call[1] === "QUESTION").map((call) => call[2])).toEqual([q1, q2]);
    fireEvent.wheel(view.container.querySelector(".exam-questions")!);
    act(() => intersectionCallback([{ target: first, isIntersecting: true, intersectionRatio: 0.9 } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.getByRole("button", { name: "Go to question 1" })).toHaveAttribute("aria-current", "true");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("keeps a missing target pending until its DOM anchor appears", async () => {
    const view = render(<ReadingRunner initial={payload()} />);
    const pane = view.container.querySelector(".exam-questions")!;
    const target = pane.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;
    target.remove();
    scrolls.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));
    expect(scrolls.some((item) => item.element === pane)).toBe(false);
    pane.appendChild(target);
    await waitFor(() => expect(scrolls.some((item) => item.element === pane)).toBe(true));
  });

  it("reveals a distant chip by scrolling only the footer strip horizontally", () => {
    const view = render(<ReadingRunner initial={payload()} />);
    const strip = view.container.querySelector(".exam-question-strip") as HTMLElement;
    const chip = screen.getByRole("button", { name: "Go to question 19" });
    strip.getBoundingClientRect = () => ({ left: 100, right: 300 } as DOMRect);
    chip.getBoundingClientRect = () => ({ left: 400, right: 440 } as DOMRect);
    scrolls.length = 0;
    fireEvent.click(chip);
    expect(scrolls.some((item) => item.element === strip && item.options.left === 140 && item.options.top === undefined)).toBe(true);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("tracks manual visibility and keeps passage tabs usable", () => {
    const view = render(<ReadingRunner initial={payload()} />);
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;
    act(() => intersectionCallback([{ target, isIntersecting: true, intersectionRatio: 0.9 } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "Passage 2" }));
    expect(screen.getByText("Passage Two")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to question 19" })).toHaveAttribute("aria-current", "true");
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

  it("keeps the newest answer unsaved until acknowledged and submits only after both writes", async () => {
    vi.useFakeTimers();
    const first = deferred();
    const latest = deferred();
    vi.mocked(saveAnswer).mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise);
    const view = render(<ReadingRunner initial={payload()} />);
    const question = view.container.querySelector(`[data-question-id="${q1}"]`) as HTMLElement;
    fireEvent.click(within(question).getByRole("radio", { name: "FALSE" }));
    expect(screen.getByText("Unsaved")).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(400); });
    expect(saveAnswer).toHaveBeenCalledWith(payload().attempt.attempt_id, q1, "FALSE");
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    fireEvent.click(within(question).getByRole("radio", { name: "TRUE" }));
    expect(within(question).getByRole("radio", { name: "TRUE" })).toBeChecked();
    expect(submitAttempt).not.toHaveBeenCalled();
    first.resolve();
    await act(async () => { await Promise.resolve(); });
    expect(saveAnswer).toHaveBeenLastCalledWith(payload().attempt.attempt_id, q1, "TRUE");
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    expect(submitAttempt).not.toHaveBeenCalled();
    latest.resolve();
    await act(async () => { await Promise.resolve(); });
    expect(submitAttempt).toHaveBeenCalledTimes(1);
  });

  it("keeps a failed answer retryable and retries the latest value on the periodic flush", async () => {
    vi.useFakeTimers();
    vi.mocked(saveAnswer).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    const view = render(<ReadingRunner initial={payload()} />);
    const question = view.container.querySelector(`[data-question-id="${q1}"]`) as HTMLElement;
    fireEvent.click(within(question).getByRole("radio", { name: "FALSE" }));
    await act(async () => { vi.advanceTimersByTime(400); });
    expect(screen.getByText("Save failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry save" })).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(10_000); });
    expect(saveAnswer).toHaveBeenCalledTimes(2);
    expect(saveAnswer).toHaveBeenLastCalledWith(payload().attempt.attempt_id, q1, "FALSE");
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("blocks Submit after a failed flush and warns before leaving only while unsaved", async () => {
    vi.mocked(saveAnswer).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    const view = render(<ReadingRunner initial={payload()} />);
    const question = view.container.querySelector(`[data-question-id="${q1}"]`) as HTMLElement;
    const cleanLeave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanLeave);
    expect(cleanLeave.defaultPrevented).toBe(false);
    fireEvent.click(within(question).getByRole("radio", { name: "FALSE" }));
    const dirtyLeave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyLeave);
    expect(dirtyLeave.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByText("Save failed")).toBeInTheDocument());
    expect(submitAttempt).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    const savedLeave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(savedLeave);
    expect(savedLeave.defaultPrevented).toBe(false);
  });

  it("routes the authoritative attempt after a lost Submit response", async () => {
    const initial = payload();
    vi.mocked(submitAttempt).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "SUBMITTED" });
    render(<ReadingRunner initial={initial} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${initial.attempt.attempt_id}`));
    expect(getAttempt).toHaveBeenCalledWith(initial.attempt.attempt_id);
  });

  it("leaves an active attempt retryable when Submit failed before commit", async () => {
    const initial = payload();
    vi.mocked(submitAttempt).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "IN_PROGRESS" });
    render(<ReadingRunner initial={initial} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Please try again"));
    expect(screen.getByRole("button", { name: "Submit answers" })).toBeEnabled();
    expect(push).not.toHaveBeenCalled();
  });

  it("keeps the answer visible and reports an unknown Submit outcome when status cannot be fetched", async () => {
    const initial = payload();
    vi.mocked(submitAttempt).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    vi.mocked(getAttempt).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    const view = render(<ReadingRunner initial={initial} />);
    const question = view.container.querySelector(`[data-question-id="${q1}"]`) as HTMLElement;
    fireEvent.click(within(question).getByRole("radio", { name: "FALSE" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("couldn't confirm"));
    expect(within(question).getByRole("radio", { name: "FALSE" })).toBeChecked();
    expect(push).not.toHaveBeenCalled();
  });

  it("routes the backend auto-finalized attempt when the countdown reaches zero", async () => {
    const initial = payload();
    initial.attempt.timer_mode = "COUNTDOWN";
    initial.attempt.deadline_at = new Date(Date.now() - 1000).toISOString();
    vi.mocked(submitAttempt).mockRejectedValueOnce(new ApiError("ATTEMPT_EXPIRED", "expired", 409));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "AUTO_SUBMITTED" });
    render(<ReadingRunner initial={initial} />);
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${initial.attempt.attempt_id}`));
    expect(submitAttempt).toHaveBeenCalledTimes(1);
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
