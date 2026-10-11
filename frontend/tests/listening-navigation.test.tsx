import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { ExamDraftStore } from "@/features/exam/exam-draft-recovery";
import { getAttempt, recordNavigation, saveAnswer } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import type { ExamPayload, Highlight } from "@/lib/api/exam";
import { createHighlight, deleteAllHighlights, deleteHighlight, saveFlag, submitAttempt } from "@/lib/api/exam";
import { renderWithLocale } from "./locale-test-utils";

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

const attemptId = "22222222-2222-4222-8222-222222222222";
const part1 = "44444444-4444-4444-8444-444444444401";
const part2 = "44444444-4444-4444-8444-444444444402";
const q1 = "11111111-1111-4111-8111-111111111101";
const q2 = "11111111-1111-4111-8111-111111111102";
const q3 = "11111111-1111-4111-8111-111111111103";
const q15 = "11111111-1111-4111-8111-111111111115";
const q25 = "11111111-1111-4111-8111-111111111125";
const q40 = "11111111-1111-4111-8111-111111111140";

function highlight(questionId = q1): Highlight {
  return { id: "99999999-9999-4999-8999-999999999999", target_kind: "QUESTION_PROMPT", target_id: questionId, segment_id: null, passage_id: null, start_block_id: null, end_block_id: null, start_offset: 0, end_offset: 9, selected_text: "Statement", created_at: new Date().toISOString() };
}

function selectStatement(element: HTMLElement) {
  const range = document.createRange();
  range.setStart(element.firstChild!, 0);
  range.setEnd(element.firstChild!, 9);
  Object.defineProperty(range, "getBoundingClientRect", { value: () => ({ left: 10, top: 20, width: 40, height: 10 }) });
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  fireEvent.mouseUp(element);
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<Awaited<ReturnType<typeof saveAnswer>>>((done) => { resolve = () => done({ question_id: q2, value: "TRUE", is_correct: true, saved_at: new Date().toISOString(), revision: 1 }); });
  return { promise, resolve };
}

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
      answer_revision: question.value === null ? 0 : 1,
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
    listening_audio_asset: { id: "77777777-7777-4777-8777-777777777777", original_name: "audio.mp3", mime_type: "audio/mpeg", file_size: 128, content_url: "/assets/77777777-7777-4777-8777-777777777777/content" },
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
          group("66666666-6666-4666-8666-666666666612", 1, [{ id: q3, number: 3, value: null, flagged: false }]),
          group("66666666-6666-4666-8666-666666666611", 0, [{ id: q1, number: 1, value: "TRUE", flagged: false }, { id: q2, number: 2, value: null, flagged: false }]),
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

function multiSlotPayload(): ExamPayload {
  const initial = payload();
  const part = initial.listening_parts.find((item) => item.id === part1)!;
  const multi = part.question_groups.find((item) => item.order_index === 0)!;
  multi.question_type = "multiple_choice_multiple";
  multi.questions = [{ ...multi.questions[0], value: [], answer_revision: 0, config: {
    min_selections: 2, max_selections: 2,
    options: [{ id: "a", label: "A", text: "Fictional option A" }, { id: "b", label: "B", text: "Fictional option B" }, { id: "c", label: "C", text: "Fictional option C" }],
  } }];
  return initial;
}

describe("Listening attempt sidebar navigation", () => {
  const scrolled: Array<{ element: HTMLElement; options: ScrollToOptions }> = [];
  let intersectionCallback: IntersectionObserverCallback = () => undefined;
  let observerCount = 0;

  beforeEach(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
    Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: vi.fn() });
    sessionStorage.clear();
    vi.clearAllMocks();
    scrolled.length = 0;
    observerCount = 0;
    vi.mocked(saveAnswer).mockImplementation(async (_attempt, questionId, value, expectedRevision) => ({ question_id: questionId, value, is_correct: null, saved_at: new Date().toISOString(), revision: expectedRevision + 1 }));
    vi.mocked(saveFlag).mockResolvedValue(undefined);
    vi.mocked(deleteHighlight).mockResolvedValue(undefined);
    vi.mocked(deleteAllHighlights).mockResolvedValue(undefined);
    vi.mocked(recordNavigation).mockResolvedValue(undefined);
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(function (this: HTMLElement, options: ScrollToOptions) {
        scrolled.push({ element: this, options });
        if (options.top !== undefined) this.scrollTop = options.top;
        if (options.left !== undefined) this.scrollLeft = options.left;
      }),
    });
    Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    class MockIntersectionObserver {
      readonly root = null;
      readonly rootMargin = "0px";
      readonly thresholds = [0.35, 0.65];
      constructor(callback: IntersectionObserverCallback) { intersectionCallback = callback; observerCount += 1; }
      disconnect() {}
      observe() {}
      takeRecords(): IntersectionObserverEntry[] { return []; }
      unobserve() {}
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  });

  afterEach(() => vi.useRealTimers());

  it.each(["normal", "full", "mock", "focused"] as const)("places %s Listening content beside a utility rail with canonical navigation and submit", (mode) => {
    const initial = payload();
    if (mode !== "normal") initial.attempt = { ...initial.attempt, scope: mode === "focused" ? "FOCUSED_UNIT" : "FULL_MODULE", attempt_context: mode === "mock" ? "FULL_MOCK" : "STANDALONE" };
    if (mode === "focused") initial.listening_parts = initial.listening_parts.filter((part) => part.id === part1);
    const view = render(<ListeningRunner initial={initial} />);
    const pane = screen.getByRole("main");
    const sidebar = screen.getByRole("complementary", { name: "Question navigation" });
    const questionNavigation = within(sidebar).getByRole("navigation", { name: "Question navigation" });

    if (mode === "focused") expect(screen.queryByRole("navigation", { name: "Section navigation" })).not.toBeInTheDocument();
    else {
      const sectionNavigation = within(sidebar).getByRole("navigation", { name: "Section navigation" });
      expect(within(sectionNavigation).getAllByRole("button").map((button) => button.textContent)).toEqual(["Section 1", "Section 2", "Section 3", "Section 4"]);
    }
    expect(within(questionNavigation).getAllByRole("button", { name: /Go to question/ }).map((button) => button.textContent)).toEqual(mode === "focused" ? ["1", "2", "3"] : ["1", "2", "3", "15", "25", "40"]);
    expect(within(questionNavigation).getAllByRole("group").map((section) => section.getAttribute("aria-label"))).toEqual(mode === "focused" ? ["Section 1"] : ["Section 1", "Section 2", "Section 3", "Section 4"]);
    expect(within(sidebar).getByRole("button", { name: "Go to question 1" })).toHaveAttribute("aria-current", "true");
    expect(sidebar.querySelector(`[data-nav-question-id="${q1}"]`)).toHaveClass("answered", "current");
    expect(sidebar.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("unanswered");
    if (mode !== "focused") expect(sidebar.querySelector(`[data-nav-question-id="${q25}"]`)).toHaveClass("flagged");
    expect(within(sidebar).getByRole("button", { name: "Submit answers" })).toBeInTheDocument();
    const previous = within(sidebar).getByRole("button", { name: "Previous question" });
    const next = within(sidebar).getByRole("button", { name: "Next question" });
    expect(previous).toBeDisabled(); expect(next).toBeEnabled();
    for (const button of [previous, next]) {
      expect(button.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
      expect(button).toHaveTextContent(/^$/);
    }
    expect(pane.parentElement).toHaveClass("listening-attempt-body");
    expect(sidebar.parentElement).toBe(pane.parentElement);
    expect(pane).toHaveTextContent("Statement 1");
    expect(view.container.querySelector(".exam-question-strip, .exam-footer, .listening-lower-dock")).toBeNull();
    expect(view.container.querySelector(".exam-flags")).not.toBeInTheDocument();
    expect(pane).not.toContainElement(questionNavigation);
  });

  it("places only audio controls in the bottom dock after the question content and sidebar", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const dock = view.container.querySelector(".listening-audio-dock") as HTMLElement;
    expect(dock).toHaveClass("listening-audio-dock");
    expect(view.container.querySelector(".listening-attempt-body")?.nextElementSibling).toBe(dock);
    expect(dock.querySelector(".listening-player-exam-bar")).toBeInTheDocument();
    expect(within(dock).queryByRole("navigation")).not.toBeInTheDocument();
    expect(within(dock).queryByRole("button", { name: "Submit answers" })).not.toBeInTheDocument();
    expect(within(dock).queryByRole("button", { name: "Previous question" })).not.toBeInTheDocument();
    expect(within(dock).queryByRole("button", { name: "Next question" })).not.toBeInTheDocument();
    const audio = dock.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { configurable: true, value: 120 }); fireEvent.loadedMetadata(audio);
    audio.currentTime = 42; fireEvent.timeUpdate(audio);
    expect(dock.querySelector(".player-progress-row")).toContainElement(within(dock).getByRole("slider", { name: "Audio seek" }));
    expect(dock).toHaveTextContent("00:42 / 02:00");
    for (const name of ["Mute", "Rewind 5 seconds", "Play audio", "Forward 5 seconds"]) expect(within(dock).getByRole("button", { name })).toBeInTheDocument();
    expect(within(dock).getByRole("slider", { name: "Volume" })).toBeInTheDocument();
    expect(within(dock).getByRole("combobox", { name: "Playback speed" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Skip introduction|Bỏ qua giới thiệu/i })).not.toBeInTheDocument();
  });

  it.each(["normal", "full", "mock", "focused"] as const)("sequential controls follow the existing %s slot order and stop at both endpoints", (mode) => {
    const initial = payload();
    if (mode !== "normal") initial.attempt = { ...initial.attempt, scope: mode === "focused" ? "FOCUSED_UNIT" : "FULL_MODULE", attempt_context: mode === "mock" ? "FULL_MOCK" : "STANDALONE" };
    if (mode === "mock") initial.audio_policy = { allow_seeking: false, allow_speed: false };
    if (mode === "focused") initial.listening_parts = initial.listening_parts.filter((part) => part.id === part1);
    const view = render(<ListeningRunner initial={initial} />);
    const rail = screen.getByRole("complementary", { name: "Question navigation" });
    const previous = within(rail).getByRole("button", { name: "Previous question" });
    const next = within(rail).getByRole("button", { name: "Next question" });
    const numbers = within(rail).getAllByRole("button", { name: /Go to question/ }).map((button) => button.textContent);
    expect(previous).toBeDisabled();
    for (const number of numbers.slice(1)) {
      fireEvent.click(next);
      expect(within(rail).getByRole("button", { name: `Go to question ${number}` })).toHaveAttribute("aria-current", "true");
      expect(previous).toBeEnabled();
    }
    expect(next).toBeDisabled();
    fireEvent.click(next);
    expect(submitAttempt).not.toHaveBeenCalled();
    for (const number of numbers.slice(0, -1).reverse()) {
      fireEvent.click(previous);
      expect(within(rail).getByRole("button", { name: `Go to question ${number}` })).toHaveAttribute("aria-current", "true");
    }
    expect(previous).toBeDisabled();
    fireEvent.click(previous);
    expect(within(rail).getByRole("button", { name: "Go to question 1" })).toHaveAttribute("aria-current", "true");
    expect(submitAttempt).not.toHaveBeenCalled();
    expect(view.container.querySelector(".listening-audio-dock")?.querySelector(".listening-sequential-navigation")).toBeNull();
    if (mode === "mock") { expect(screen.getByLabelText("Audio seek")).toBeDisabled(); expect(screen.getByLabelText("Playback speed")).toBeDisabled(); }
  });

  it("sequential navigation crosses group and section boundaries through the existing navigation activity records", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const next = screen.getByRole("button", { name: "Next question" });
    const previous = screen.getByRole("button", { name: "Previous question" });
    fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(next);
    expect(view.container.querySelector(`[data-question-id="${q3}"]`)).toBeInTheDocument();
    fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Section 2" })).toHaveAttribute("aria-current", "page");
    expect(view.container.querySelector(`[data-question-id="${q15}"]`)).toBeInTheDocument();
    fireEvent.click(previous);
    expect(screen.getByRole("button", { name: "Section 1" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Go to question 3" })).toHaveAttribute("aria-current", "true");
    expect(vi.mocked(recordNavigation).mock.calls.filter((call) => call[1] === "QUESTION").map((call) => call[2])).toEqual([q1, q2, q3, q15, q3]);
    expect(vi.mocked(recordNavigation).mock.calls.filter((call) => call[1] === "LISTENING_PART").map((call) => call[2])).toEqual([part1, part2, part1]);
    expect(submitAttempt).not.toHaveBeenCalled();
  });

  it("sequential navigation visits each multi-slot number without changing shared question tracking or recording duplicate navigation", () => {
    const view = render(<ListeningRunner initial={multiSlotPayload()} />);
    const next = screen.getByRole("button", { name: "Next question" });
    const previous = screen.getByRole("button", { name: "Previous question" });
    const group = view.container.querySelector("[data-question-group-id]");
    const controls = [...view.container.querySelectorAll('input[type="checkbox"]')];
    fireEvent.click(next);
    expect(previous).toBeEnabled();
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(view.container.querySelector("[data-question-group-id]")).toBe(group);
    expect([...view.container.querySelectorAll('input[type="checkbox"]')]).toEqual(controls);
    expect(vi.mocked(recordNavigation).mock.calls.filter((call) => call[1] === "QUESTION")).toHaveLength(1);
    fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Go to question 3" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(previous);
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(previous).toBeEnabled();
    fireEvent.click(previous);
    expect(previous).toBeDisabled();
    expect(vi.mocked(recordNavigation).mock.calls.filter((call) => call[1] === "QUESTION").map((call) => call[2])).toEqual([q1, q3, q1]);
  });

  it("numbered multi-slot buttons and manual section selection anchor the same sequential cursor", () => {
    render(<ListeningRunner initial={multiSlotPayload()} />);
    const next = screen.getByRole("button", { name: "Next question" });
    const previous = screen.getByRole("button", { name: "Previous question" });
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));
    expect(previous).toBeEnabled();
    fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Go to question 3" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(previous);
    expect(previous).toBeEnabled();
    fireEvent.focus(screen.getAllByRole("checkbox")[0]);
    expect(previous).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Section 1" }));
    expect(previous).toBeDisabled();
    fireEvent.click(next); fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Go to question 3" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "Go to question 1" }));
    expect(previous).toBeDisabled();
  });

  it("sequential navigation preserves the selected multi-slot number while answering its shared question", async () => {
    render(<ListeningRunner initial={multiSlotPayload()} />);
    const next = screen.getByRole("button", { name: "Next question" });
    const previous = screen.getByRole("button", { name: "Previous question" });
    fireEvent.click(next);
    fireEvent.click(screen.getByRole("checkbox", { name: "A. Fictional option A" }));
    expect(previous).toBeEnabled();
    fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Go to question 3" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(previous);
    expect(screen.getByRole("checkbox", { name: "A. Fictional option A" })).toBeChecked();
    expect(previous).toBeEnabled();
    fireEvent.click(previous); expect(previous).toBeDisabled();
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledExactlyOnceWith(attemptId, q1, ["a"], 0));
  });

  it("sequential navigation crosses a section boundary after the last slot of a shared question", () => {
    const initial = multiSlotPayload();
    const part = initial.listening_parts.find((item) => item.id === part1)!;
    part.question_groups = part.question_groups.filter((item) => item.order_index === 0);
    render(<ListeningRunner initial={initial} />);
    const next = screen.getByRole("button", { name: "Next question" });
    const previous = screen.getByRole("button", { name: "Previous question" });
    fireEvent.click(next); fireEvent.click(next);
    expect(screen.getByRole("button", { name: "Section 2" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Go to question 15" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(previous);
    expect(screen.getByRole("button", { name: "Section 1" })).toHaveAttribute("aria-current", "page");
    expect(previous).toBeEnabled();
    fireEvent.click(previous); expect(previous).toBeDisabled();
  });

  it("sequential navigation disables Next on the last slot even when a focused attempt has only one shared question", () => {
    const initial = multiSlotPayload();
    initial.attempt = { ...initial.attempt, scope: "FOCUSED_UNIT" };
    initial.listening_parts = initial.listening_parts.filter((item) => item.id === part1);
    initial.listening_parts[0].question_groups = initial.listening_parts[0].question_groups.filter((item) => item.order_index === 0);
    render(<ListeningRunner initial={initial} />);
    const next = screen.getByRole("button", { name: "Next question" });
    const previous = screen.getByRole("button", { name: "Previous question" });
    expect(previous).toBeDisabled(); expect(next).toBeEnabled();
    fireEvent.click(next); expect(previous).toBeEnabled(); expect(next).toBeDisabled();
    fireEvent.click(next); expect(submitAttempt).not.toHaveBeenCalled();
    fireEvent.click(previous); expect(previous).toBeDisabled(); expect(next).toBeEnabled();
  });

  it("sequential navigation preserves a pending answer save, timer, highlights, flags and audio state", async () => {
    vi.useFakeTimers();
    const initial = payload();
    initial.highlights = [highlight(q2)];
    initial.listening_parts.find((item) => item.id === part1)!.question_groups.find((item) => item.order_index === 0)!.questions[1].flagged = true;
    const pending = deferred();
    vi.mocked(saveAnswer).mockReturnValueOnce(pending.promise);
    const view = render(<ListeningRunner initial={initial} />);
    const audio = view.container.querySelector("audio")!;
    const dock = view.container.querySelector(".listening-audio-dock");
    const timer = view.container.querySelector(".exam-timer");
    const timerText = timer?.textContent;
    Object.defineProperty(audio, "duration", { configurable: true, value: 120 }); fireEvent.loadedMetadata(audio);
    fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Playback speed"), { target: { value: "1.5" } });
    fireEvent.change(screen.getByLabelText("Volume"), { target: { value: "0.35" } });
    fireEvent.click(screen.getByRole("button", { name: "Mute" })); fireEvent.play(audio);
    fireEvent.click(within(view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement).getByRole("radio", { name: "TRUE" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    const resets = [audio.pause, audio.load].map((method) => vi.mocked(method).mock.calls.length);
    for (const direction of ["Next question", "Next question", "Previous question", "Previous question"]) {
      fireEvent.click(screen.getByRole("button", { name: direction }));
      expect(view.container.querySelector("audio")).toBe(audio);
      expect(view.container.querySelector(".listening-audio-dock")).toBe(dock);
      expect([audio.currentTime, audio.playbackRate, audio.volume, audio.muted]).toEqual([42, 1.5, 0.35, true]);
      expect([audio.pause, audio.load].map((method) => vi.mocked(method).mock.calls.length)).toEqual(resets);
      expect(view.container.querySelector(".exam-timer")).toBe(timer); expect(timer).toHaveTextContent(timerText!);
      expect(screen.getByRole("button", { name: "Pause audio" })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(within(view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement).getByRole("radio", { name: "TRUE" })).toBeChecked();
    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("flagged", "answered");
    expect(view.container.querySelector(`[data-question-id="${q2}"] mark`)).toHaveTextContent("Statement");
    expect(saveAnswer).toHaveBeenCalledExactlyOnceWith(attemptId, q2, "TRUE", 0);
    expect(submitAttempt).not.toHaveBeenCalled();
    await act(async () => { pending.resolve(); });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(saveAnswer).toHaveBeenCalledOnce();
  });

  it("sequential controls localize without resetting the current shared-question slot", () => {
    localStorage.clear();
    const view = renderWithLocale(<ListeningRunner initial={multiSlotPayload()} />);
    fireEvent.click(screen.getByRole("button", { name: "Next question" }));
    const audio = view.container.querySelector("audio");
    const records = [...vi.mocked(recordNavigation).mock.calls];
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByRole("button", { name: "Câu trước" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Câu tiếp theo" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Đến câu hỏi 2" })).toHaveAttribute("aria-current", "true");
    expect(vi.mocked(recordNavigation).mock.calls).toEqual(records);
    fireEvent.click(screen.getByRole("button", { name: "Câu tiếp theo" }));
    expect(screen.getByRole("button", { name: "Đến câu hỏi 3" })).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "Câu trước" }));
    fireEvent.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(screen.getByRole("button", { name: "Previous question" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous question" }));
    expect(screen.getByRole("button", { name: "Previous question" })).toBeDisabled();
    expect(view.container.querySelector("audio")).toBe(audio);
  });

  it("groups all forty full-test question buttons by section in the right rail", () => {
    const initial = payload();
    initial.attempt = { ...initial.attempt, scope: "FULL_MODULE", attempt_context: "STANDALONE" };
    initial.listening_parts = [...initial.listening_parts].sort((left, right) => left.order_index - right.order_index).map((part, index) => ({
      ...part,
      question_groups: [group(`full-group-${index}`, 0, Array.from({ length: 10 }, (_, offset) => {
        const number = index * 10 + offset + 1;
        return { id: `11111111-1111-4111-8111-${String(number).padStart(12, "0")}`, number, value: null, flagged: false };
      }))],
    }));
    const view = render(<ListeningRunner initial={initial} />);
    const rail = screen.getByRole("complementary", { name: "Question navigation" });
    const navigation = within(rail).getByRole("navigation", { name: "Question navigation" });
    expect(within(navigation).getAllByRole("button", { name: /Go to question/ })).toHaveLength(40);
    within(navigation).getAllByRole("group").forEach((section, index) => {
      expect(within(section).getAllByRole("button", { name: /Go to question/ }).map((button) => button.textContent)).toEqual(Array.from({ length: 10 }, (_, offset) => String(index * 10 + offset + 1)));
    });
    const audio = view.container.querySelector("audio");
    fireEvent.click(within(rail).getByRole("button", { name: "Go to question 40" }));
    expect(screen.getByRole("main")).toHaveTextContent("Statement 40");
    expect(within(rail).getByRole("button", { name: "Go to question 40" })).toHaveAttribute("aria-current", "true");
    expect(within(rail).getByRole("button", { name: "Section 4" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(within(rail).getByRole("button", { name: "Section 2" }));
    expect(within(rail).getByRole("button", { name: "Go to question 11" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("main")).toHaveTextContent("Statement 11");
    expect(view.container.querySelector("audio")).toBe(audio);
  });

  it("preserves the current question, answers, flags and player state through a shell rerender", async () => {
    const initial = payload();
    const view = render(<ListeningRunner initial={initial} />);
    const sidebar = screen.getByRole("complementary", { name: "Question navigation" });
    const audio = view.container.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { configurable: true, value: 120 }); fireEvent.loadedMetadata(audio);
    fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Playback speed"), { target: { value: "1.5" } });
    fireEvent.change(screen.getByLabelText("Volume"), { target: { value: "0.35" } });
    fireEvent.click(screen.getByRole("button", { name: "Mute" })); fireEvent.play(audio);
    fireEvent.click(within(view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement).getByRole("radio", { name: "FALSE" }));
    fireEvent.click(within(sidebar).getByRole("button", { name: "Flag question 2" }));
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q2, "FALSE", 0));
    const calls = [audio.pause, audio.load, saveAnswer, saveFlag, recordNavigation].map((method) => vi.mocked(method).mock.calls.length);
    view.rerender(<ListeningRunner initial={initial} />);
    expect(screen.getByRole("complementary", { name: "Question navigation" })).toBe(sidebar);
    expect(view.container.querySelector("audio")).toBe(audio);
    expect([audio.currentTime, audio.playbackRate, audio.volume, audio.muted]).toEqual([42, 1.5, 0.35, true]);
    expect(screen.getByRole("button", { name: "Pause audio" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unmute" })).toBeInTheDocument();
    expect(screen.getByLabelText("Playback speed")).toHaveValue("1.5");
    expect(screen.getByLabelText("Volume")).toHaveValue("0.35");
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(sidebar.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("current", "answered", "flagged");
    expect(within(view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement).getByRole("radio", { name: "FALSE" })).toBeChecked();
    expect([audio.pause, audio.load, saveAnswer, saveFlag, recordNavigation].map((method) => vi.mocked(method).mock.calls.length)).toEqual(calls);
  });

  it("keeps the dock, player, media state and reset counts while navigating groups and sections", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const dock = view.container.querySelector(".listening-audio-dock");
    expect(dock).toBeInTheDocument();
    const player = view.container.querySelector(".listening-player"); const audio = view.container.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { configurable: true, value: 120 }); fireEvent.loadedMetadata(audio);
    audio.currentTime = 42; audio.playbackRate = 1.5; audio.volume = 0.35; audio.muted = true; fireEvent.timeUpdate(audio);
    const resets = [audio.pause, audio.load].map((method) => vi.mocked(method).mock.calls.length);
    for (const name of ["Go to question 2", "Go to question 3", "Section 2", "Go to question 25"]) {
      fireEvent.click(screen.getByRole("button", { name }));
      expect(view.container.querySelector(".listening-audio-dock")).toBe(dock); expect(view.container.querySelector(".listening-player")).toBe(player); expect(view.container.querySelector("audio")).toBe(audio);
      expect([audio.currentTime, audio.playbackRate, audio.volume, audio.muted]).toEqual([42, 1.5, 0.35, true]);
      expect([audio.pause, audio.load].map((method) => vi.mocked(method).mock.calls.length)).toEqual(resets);
    }
    expect(screen.getByRole("button", { name: "Go to question 25" })).toHaveAttribute("aria-current", "true");
  });

  it("shows answered, unanswered, flagged, and current states", () => {
    const view = render(<ListeningRunner initial={payload()} />);

    expect(view.container.querySelector(`[data-nav-question-id="${q1}"]`)).toHaveClass("answered", "current");
    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("unanswered");
    expect(view.container.querySelector(`[data-nav-question-id="${q25}"]`)).toHaveClass("unanswered", "flagged");
  });

  it("navigates within the current Section using only the question pane", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    scrolled.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));

    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;
    expect(scrolled.some((item) => item.element === view.container.querySelector(".listening-question-pane") && item.options.top !== undefined)).toBe(true);
    expect(target).toHaveClass("is-navigation-target");
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("renders only the active group and switches groups from question navigation", async () => {
    const view = render(<ListeningRunner initial={payload()} />);

    expect(view.container.querySelector(`[data-question-id="${q1}"]`)).toBeInTheDocument();
    expect(view.container.querySelector(`[data-question-id="${q2}"]`)).toBeInTheDocument();
    expect(view.container.querySelector(`[data-question-id="${q3}"]`)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Go to question 3" }));

    await waitFor(() => expect(view.container.querySelector(`[data-question-id="${q3}"]`)).toBeInTheDocument());
    expect(view.container.querySelector(`[data-question-id="${q1}"]`)).not.toBeInTheDocument();
    expect(view.container.querySelectorAll("[data-question-group-id]")).toHaveLength(1);
    expect(scrolled.some((item) => item.element === view.container.querySelector(".listening-question-pane") && item.options.top !== undefined)).toBe(true);
  });

  it("keeps the same group and audio DOM mounted for navigation inside a group", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const groupBefore = view.container.querySelector("[data-question-group-id]");
    const audioBefore = view.container.querySelector(".listening-player");

    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));

    expect(view.container.querySelector("[data-question-group-id]")).toBe(groupBefore);
    expect(view.container.querySelector(".listening-player")).toBe(audioBefore);
  });

  it("restores saved question highlights across groups and Sections", async () => {
    const initial = payload();
    initial.highlights = [highlight()];
    const view = render(<ListeningRunner initial={initial} />);
    const audio = view.container.querySelector(".listening-player");

    expect(screen.getByText("1 highlight")).toBeInTheDocument();
    expect(view.container.querySelector(`[data-question-id="${q1}"] mark`)).toHaveTextContent("Statement");
    fireEvent.click(screen.getByRole("button", { name: "Go to question 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Section 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Section 1" }));

    expect(await waitFor(() => view.container.querySelector(`[data-question-id="${q1}"] mark`))).toHaveTextContent("Statement");
    expect(screen.getByText("1 highlight")).toBeInTheDocument();
    expect(view.container.querySelector(".listening-player")).toBe(audio);
  });

  it("creates a semantic question highlight without remounting audio or changing answers", async () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const audio = view.container.querySelector(".listening-player");
    vi.mocked(createHighlight).mockResolvedValueOnce(highlight());
    const text = view.container.querySelector(`[data-question-id="${q1}"] [data-highlight-target]`) as HTMLElement;
    selectStatement(text);
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));

    await waitFor(() => expect(createHighlight).toHaveBeenCalledWith(attemptId, {
      target_kind: "QUESTION_PROMPT", target_id: q1, start_offset: 0, end_offset: 9, selected_text: "Statement",
    }));
    expect(await screen.findByText("1 highlight")).toBeInTheDocument();
    expect(text.querySelector("mark")).toHaveTextContent("Statement");
    expect(view.container.querySelector(".listening-player")).toBe(audio);
    fireEvent.click(within(view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement).getByRole("radio", { name: "FALSE" }));
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q2, "FALSE", 0));
  });

  it("removes one saved highlight only after the delete API succeeds", async () => {
    const initial = payload();
    initial.highlights = [highlight()];
    const view = render(<ListeningRunner initial={initial} />);
    fireEvent.click(screen.getByRole("button", { name: "Highlight: Statement. Open options" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove highlight" }));

    await waitFor(() => expect(deleteHighlight).toHaveBeenCalledWith(attemptId, initial.highlights[0].id));
    expect(await screen.findByText("0 highlights")).toBeInTheDocument();
    expect(view.container.querySelector(`[data-question-id="${q1}"] mark`)).not.toBeInTheDocument();
  });

  it("confirms Delete all and clears saved highlights after success", async () => {
    const initial = payload();
    initial.highlights = [highlight()];
    const view = render(<ListeningRunner initial={initial} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete all" }));
    expect(screen.getByRole("dialog", { name: "Delete all highlights?" })).toHaveTextContent("All highlights in this attempt will be removed. This action cannot be undone.");
    expect(deleteAllHighlights).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete all highlights" }));

    await waitFor(() => expect(deleteAllHighlights).toHaveBeenCalledWith(attemptId));
    expect(await screen.findByText("0 highlights")).toBeInTheDocument();
    expect(view.container.querySelector(`[data-question-id="${q1}"] mark`)).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Delete all highlights?" })).not.toBeInTheDocument();
  });

  it("keeps highlights and offers retry when Delete all fails", async () => {
    const initial = payload();
    initial.highlights = [highlight()];
    vi.mocked(deleteAllHighlights).mockRejectedValueOnce(new Error("offline"));
    const view = render(<ListeningRunner initial={initial} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete all" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete all highlights" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not delete the highlights");
    expect(screen.getByText("1 highlight")).toBeInTheDocument();
    expect(view.container.querySelector(`[data-question-id="${q1}"] mark`)).toHaveTextContent("Statement");
    fireEvent.click(screen.getByRole("button", { name: "Delete all highlights" }));
    await waitFor(() => expect(deleteAllHighlights).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("0 highlights")).toBeInTheDocument();
  });

  it("preserves answers and flags while switching question groups", async () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const q2Target = view.container.querySelector(`[data-question-id="${q2}"]`)!;
    fireEvent.click(within(q2Target as HTMLElement).getByRole("radio", { name: "FALSE" }));
    fireEvent.click(screen.getByRole("button", { name: "Flag question 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Go to question 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));

    const restored = await waitFor(() => view.container.querySelector(`[data-question-id="${q2}"]`)!);
    expect(within(restored as HTMLElement).getByRole("radio", { name: "FALSE" })).toBeChecked();
    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("flagged", "answered");
  });

  it.each(["map_labelling", "plan_labelling", "diagram_labelling"])("uses the visual and answer panes for %s", (questionType) => {
    const data = payload();
    const source = data.listening_parts.find((item) => item.id === part1)!;
    const visual = source.question_groups.find((item) => item.questions.some((question) => question.id === q1)) as typeof source.question_groups[number] & { image_asset?: NonNullable<ExamPayload["listening_audio_asset"]> };
    visual.question_type = questionType;
    visual.image_asset = { id: "88888888-8888-4888-8888-888888888888", original_name: "visual.png", mime_type: "image/png", file_size: 256, content_url: "/assets/88888888-8888-4888-8888-888888888888/content" };
    visual.config = questionType === "diagram_labelling"
      ? { items: visual.questions.map((question, index) => ({ id: `item-${index}`, question_id: question.id, box: { x: .1, y: .1 + index * .2, width: .2 }, arrow: { start_x: .2, start_y: .2, end_x: .3, end_y: .3 } })) }
      : { options: [{ id: "99999999-9999-4999-8999-999999999991", label: "A", text: "Location A" }, { id: "99999999-9999-4999-8999-999999999992", label: "B", text: "Location B" }] };

    const view = render(<ListeningRunner initial={data} />);

    expect(view.container.querySelector(".listening-visual-layout")).toBeInTheDocument();
    expect(view.container.querySelector(".listening-visual-pane")).toBeInTheDocument();
    expect(view.container.querySelector(".listening-visual-answer-pane")).toBeInTheDocument();
    scrolled.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));
    expect(view.container.querySelector(`.listening-visual-answer-pane [data-question-id="${q2}"]`)).toHaveClass("is-navigation-target");
    expect(scrolled.some((item) => item.element === view.container.querySelector(".listening-question-pane"))).toBe(true);
  });

  it("keeps non-visual groups in the normal layout", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    expect(view.container.querySelector(".listening-visual-layout")).not.toBeInTheDocument();
    expect(view.container.querySelector(".listening-question-pane")).not.toHaveClass("listening-question-pane-visual");
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
    await waitFor(() => expect(scrolled.some((item) => item.element === view.container.querySelector(".listening-question-pane") && item.options.top !== undefined)).toBe(true));
    expect(target).toHaveClass("is-navigation-target");
    expect(screen.getByRole("button", { name: "Go to question 15" })).toHaveAttribute("aria-current", "true");
    await waitFor(() => expect(recordNavigation).toHaveBeenCalledWith(attemptId, "LISTENING_PART", part2));
    expect(recordNavigation).toHaveBeenCalledWith(attemptId, "QUESTION", q15);
  });

  it("updates the answered chip immediately and preserves answer autosave", async () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;

    fireEvent.click(within(target as HTMLElement).getByRole("radio", { name: "FALSE" }));

    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("answered", "current");
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q2, "FALSE", 0), { timeout: 1200 });
  });

  it("restores a Listening answer into navigation and saves with its base revision", async () => {
    const initial = payload();
    const store = new ExamDraftStore(initial.attempt);
    store.saveEntry(q2, "FALSE", 0);
    const view = render(<ListeningRunner initial={initial} />);
    const target = view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement;
    await waitFor(() => expect(within(target).getByRole("radio", { name: "FALSE" })).toBeChecked());
    expect(view.container.querySelector(`[data-nav-question-id="${q2}"]`)).toHaveClass("answered");
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q2, "FALSE", 0));
    await waitFor(() => expect(store.load()).toBeNull());
  });

  it("keeps an edited answer across navigation and waits for its latest save before Submit", async () => {
    vi.useFakeTimers();
    const first = deferred();
    const latest = deferred();
    vi.mocked(saveAnswer).mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise);
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement;
    fireEvent.click(within(target).getByRole("radio", { name: "FALSE" }));
    await act(async () => { vi.advanceTimersByTime(400); });
    fireEvent.click(within(target).getByRole("radio", { name: "TRUE" }));
    fireEvent.click(screen.getByRole("button", { name: "Section 2" }));
    expect(screen.getByText("Section Two")).toBeInTheDocument();
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    expect(submitAttempt).not.toHaveBeenCalled();
    first.resolve();
    await act(async () => { await Promise.resolve(); });
    expect(saveAnswer).toHaveBeenLastCalledWith(attemptId, q2, "TRUE", 1);
    expect(submitAttempt).not.toHaveBeenCalled();
    latest.resolve();
    await act(async () => { await Promise.resolve(); });
    expect(submitAttempt).toHaveBeenCalledTimes(1);
  });

  it("blocks Submit on a failed latest answer and offers Retry", async () => {
    vi.mocked(saveAnswer).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0));
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement;
    fireEvent.click(within(target).getByRole("radio", { name: "FALSE" }));
    expect(screen.getByText("Unsaved")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByText("Save failed")).toBeInTheDocument());
    expect(submitAttempt).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    expect(saveAnswer).toHaveBeenLastCalledWith(attemptId, q2, "FALSE", 0);
  });

  it("advances the Listening answer token after the first save", async () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement;
    fireEvent.click(within(target).getByRole("radio", { name: "FALSE" }));
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q2, "FALSE", 0));
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    fireEvent.click(within(target).getByRole("radio", { name: "TRUE" }));
    await waitFor(() => expect(saveAnswer).toHaveBeenLastCalledWith(attemptId, q2, "TRUE", 1));
  });

  it("does not retry a conflicted Listening answer on periodic flush", async () => {
    vi.useFakeTimers();
    vi.mocked(saveAnswer).mockRejectedValueOnce(new ApiError("ATTEMPT_RESPONSE_CONFLICT", "Changed in another tab", 409));
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`[data-question-id="${q2}"]`) as HTMLElement;
    fireEvent.click(within(target).getByRole("radio", { name: "FALSE" }));
    await act(async () => { vi.advanceTimersByTime(400); });
    expect(screen.getByRole("button", { name: "Reload latest" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry save" })).not.toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(10_000); });
    expect(saveAnswer).toHaveBeenCalledTimes(1);
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

  it("tracks the current question from focus without page-level scrolling", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    scrolled.length = 0;
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;

    fireEvent.focus(within(target as HTMLElement).getByRole("radio", { name: "TRUE" }));

    const chipButton = screen.getByRole("button", { name: "Go to question 2" });
    expect(chipButton).toHaveAttribute("aria-current", "true");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("tracks the most visible question with the Reading IntersectionObserver thresholds", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;

    act(() => intersectionCallback(
      [{ target, isIntersecting: true, intersectionRatio: 0.8 } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    ));

    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(observerCount).toBe(1);
  });

  it("does not let an intermediate observer callback switch the requested group", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    fireEvent.click(screen.getByRole("button", { name: "Go to question 3" }));
    const oldTarget = document.createElement("div");
    oldTarget.dataset.questionId = q1;
    act(() => intersectionCallback([{ target: oldTarget, isIntersecting: true, intersectionRatio: 0.9 } as unknown as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(view.container.querySelector(`[data-question-id="${q3}"]`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to question 3" })).toHaveAttribute("aria-current", "true");
    expect(observerCount).toBe(2);
  });

  it("keeps a same-group navigator choice through an intermediate observer callback", () => {
    const view = render(<ListeningRunner initial={payload()} />);
    fireEvent.click(screen.getByRole("button", { name: "Go to question 2" }));
    const first = view.container.querySelector(`.exam-question-target[data-question-id="${q1}"]`)!;
    act(() => intersectionCallback([{ target: first, isIntersecting: true, intersectionRatio: 0.9 } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.getByRole("button", { name: "Go to question 2" })).toHaveAttribute("aria-current", "true");
    expect(vi.mocked(recordNavigation).mock.calls.filter((call) => call[1] === "QUESTION").map((call) => call[2])).toEqual([q1, q2]);
    fireEvent.wheel(view.container.querySelector(".listening-question-pane")!);
    act(() => intersectionCallback([{ target: first, isIntersecting: true, intersectionRatio: 0.9 } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.getByRole("button", { name: "Go to question 1" })).toHaveAttribute("aria-current", "true");
    expect(observerCount).toBe(1);
  });

  it.each([{ top: 420, bottom: 470, nextScroll: 270 }, { top: 50, bottom: 90, nextScroll: 50 }])("reveals a chip at $top by scrolling only the sidebar vertically", ({ top, bottom, nextScroll }) => {
    const view = render(<ListeningRunner initial={payload()} />);
    const rail = view.container.querySelector(".listening-navigation-scroll") as HTMLElement;
    const chip = screen.getByRole("button", { name: "Go to question 40" });
    rail.scrollTop = 100;
    rail.getBoundingClientRect = () => ({ top: 100, bottom: 300 } as DOMRect);
    chip.getBoundingClientRect = () => ({ top, bottom } as DOMRect);
    scrolled.length = 0;
    fireEvent.click(chip);
    expect(scrolled.some((item) => item.element === rail && item.options.top === nextScroll && item.options.left === undefined)).toBe(true);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
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

  it("reconciles a finalized Listening autosave without showing Save failed", async () => {
    const initial = payload();
    vi.mocked(saveAnswer).mockRejectedValueOnce(new ApiError("ATTEMPT_EXPIRED", "expired", 409));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "AUTO_SUBMITTED" });
    const view = render(<ListeningRunner initial={initial} />);
    const target = view.container.querySelector(`.exam-question-target[data-question-id="${q2}"]`)!;
    fireEvent.click(within(target as HTMLElement).getByRole("radio", { name: "FALSE" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/review/${attemptId}`), { timeout: 1500 });
    expect(screen.getByRole("status")).toHaveTextContent("Attempt finished");
    expect(screen.queryByText("Save failed")).not.toBeInTheDocument();
    expect(saveAnswer).toHaveBeenCalledTimes(1);
  });

  it.each(["none", "range", "audio"])("keeps focused Listening usable with missing %s", async (missing) => {
    const initial = payload();
    const part = initial.listening_parts[0];
    initial.attempt = { ...initial.attempt, scope: "FOCUSED_UNIT", focused_unit: { kind: "LISTENING_PART", id: part.id, order_index: 1, label: "Section 2", title: "Section Two" } };
    initial.listening_parts = [{ ...part, audio_start_seconds: missing === "range" ? null : 468, audio_end_seconds: missing === "range" ? null : 931 }];
    initial.audio_policy = { allow_seeking: true, allow_speed: true };
    if (missing === "audio") initial.listening_audio_asset = null;
    vi.mocked(submitAttempt).mockResolvedValue({} as never);
    const view = render(<ListeningRunner initial={initial} />);
    expect(screen.getByText("Focused practice · Listening")).toBeInTheDocument();
    expect(screen.getByText("Section 2 · Section Two")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Section navigation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Go to question 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to question 15" })).toBeInTheDocument();
    const audio = view.container.querySelector("audio");
    if (missing === "audio") {
      expect(audio).toBeNull();
      expect(view.container.querySelector(".listening-audio-dock")).toBeNull();
      expect(screen.queryByLabelText("Listening audio player")).not.toBeInTheDocument();
      expect(screen.getByText("No recording is attached. You can continue with the questions and use an external recording if needed.")).toHaveClass("notice");
    } else {
      expect(audio).not.toBeNull();
      expect(view.container.querySelector(".listening-audio-dock")).toContainElement(audio);
      Object.defineProperty(audio!, "duration", { configurable: true, value: 1000 });
      fireEvent.loadedMetadata(audio!);
      expect(audio!.currentTime).toBe(missing === "range" ? 0 : 468);
      expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", missing === "range" ? "1000" : "463");
      expect(screen.getByLabelText("Audio seek")).not.toBeDisabled();
      expect(screen.getByLabelText("Playback speed")).not.toBeDisabled();
      if (missing === "none") {
        fireEvent.click(screen.getByRole("button", { name: "Rewind 5 seconds" })); expect(audio!.currentTime).toBe(468);
        fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "460" } });
        fireEvent.click(screen.getByRole("button", { name: "Forward 5 seconds" })); expect(audio!.currentTime).toBe(931);
      }
      if (missing === "range") {
        expect(screen.getByText("Section audio range is not configured. Full recording is available.")).toHaveClass("notice");
        fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "950" } });
        expect(audio!.currentTime).toBe(950);
        fireEvent.change(screen.getByLabelText("Playback speed"), { target: { value: "1.5" } });
        expect(audio!.playbackRate).toBe(1.5);
      }
    }
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(view.container.querySelector(".exam-timer")).toBeInTheDocument();
    const question = view.container.querySelector(`[data-question-id="${q15}"]`)!;
    fireEvent.click(within(question as HTMLElement).getByRole("radio", { name: "FALSE" }));
    await waitFor(() => expect(saveAnswer).toHaveBeenCalledWith(attemptId, q15, "FALSE", 0));
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(submitAttempt).toHaveBeenCalledWith(attemptId));
    expect(push).toHaveBeenCalledWith(`/review/${attemptId}`);
  });

  it.each([false, true])("ignores stored ranges in full Listening (Full Mock=%s)", (mock) => {
    const initial = payload();
    initial.attempt = { ...initial.attempt, scope: "FULL_MODULE", attempt_context: mock ? "FULL_MOCK" : "STANDALONE" };
    initial.listening_parts = initial.listening_parts.map((part) => ({ ...part, audio_start_seconds: 468, audio_end_seconds: 931 }));
    initial.audio_policy = { allow_seeking: !mock, allow_speed: !mock };
    const view = render(<ListeningRunner initial={initial} />);
    const audio = view.container.querySelector("audio")!;
    Object.defineProperty(audio, "duration", { configurable: true, value: 1000 });
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(0);
    expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", "1000");
    expect(within(screen.getByRole("navigation", { name: "Section navigation" })).getAllByRole("button")).toHaveLength(4);
    expect(screen.queryByText("Section audio range is not configured. Full recording is available.")).not.toBeInTheDocument();
    if (mock) {
      expect(screen.getByLabelText("Audio seek")).toBeDisabled();
      expect(screen.getByLabelText("Playback speed")).toBeDisabled();
      expect(screen.getByText("Exam mode · Seeking locked")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Rewind 5 seconds" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Forward 5 seconds" })).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "90" } }); expect(audio.currentTime).toBe(0);
    } else {
      expect(screen.getByLabelText("Audio seek")).not.toBeDisabled();
      expect(screen.getByLabelText("Playback speed")).not.toBeDisabled();
    }
  });
});
