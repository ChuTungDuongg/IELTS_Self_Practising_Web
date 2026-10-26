import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import savedContracts from "../../backend/tests/fixtures/question-contracts.json";
import type { ExamPayload } from "@/lib/api/exam";
import type { PassageBlock, QuestionGroupModel } from "@/features/questions/types";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { rememberAttemptPresentation, rememberSessionPresentation } from "@/features/exam/attempt-presentation";
import { saveAnswer } from "@/lib/api/attempts";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/lib/api/attempts", async importOriginal => ({ ...await importOriginal<typeof import("@/lib/api/attempts")>(), recordActivity: vi.fn(), recordNavigation: vi.fn(), saveAnswer: vi.fn() }));
vi.mock("@/lib/api/exam", async importOriginal => ({ ...await importOriginal<typeof import("@/lib/api/exam")>(), createHighlight: vi.fn(), deleteHighlight: vi.fn(), deleteAllHighlights: vi.fn(), saveFlag: vi.fn() }));
type Contract = { group: QuestionGroupModel & { id: string }; passageBlocks: PassageBlock[]; response: string | string[] };
const contracts = savedContracts as unknown as Contract[];

function payload(contract: Contract, module: "READING" | "LISTENING" = "READING"): ExamPayload {
  const now = new Date().toISOString();
  const group = { ...contract.group, questions: contract.group.questions.map(question => ({ id: question.id!, number: question.number, prompt: question.prompt, config: question.config, order_index: question.order_index, value: null, flagged: false, answer_revision: 0 })) };
  return {
    attempt: { attempt_id: "22222222-2222-4222-8222-222222222222", test_version_id: "33333333-3333-4333-8333-333333333333", module, attempt_context: "STANDALONE", test_session_id: null, status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: now, paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: now, finished_at: null, elapsed_seconds: 120, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: now },
    test_title: "Fictional saved practice", highlights: [], writing_tasks: [], listening_audio_asset: null,
    audio_policy: { allow_seeking: false, allow_speed: false },
    passages: [{ id: "44444444-4444-4444-8444-444444444444", title: "Fictional passage", order_index: 0, blocks: contract.passageBlocks, question_groups: [group] }],
    listening_parts: [{ id: "55555555-5555-4555-8555-555555555555", title: "Fictional section", order_index: 0, question_groups: [group] }],
  };
}

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks(); vi.useFakeTimers();
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  vi.mocked(saveAnswer).mockImplementation(async (_attemptId, question_id, value, revision) => ({ question_id, value, revision: revision + 1, saved_at: new Date().toISOString(), is_correct: null }));
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe.each(["PRACTICE", "EXAM"] as const)("%s uses the canonical Reading controller", presentation => {
  it.each(contracts)("saves $group.question_type with the same ID, value and revision", async contract => {
    const data = payload(contract);
    rememberAttemptPresentation(data.attempt, presentation);
    const view = render(<ReadingRunner initial={data} />);
    expect(view.container.querySelector(".exam-runner")).toHaveAttribute("data-presentation", presentation);
    expect(screen.queryByRole("separator") !== null).toBe(presentation === "PRACTICE");
    const { response } = contract;
    const question = contract.group.questions[0];
    if (Array.isArray(response)) {
      const options = question.config.options as Array<{ id: string }>;
      response.forEach(id => fireEvent.click(view.container.querySelectorAll<HTMLInputElement>("input[type=checkbox]")[options.findIndex(option => option.id === id)]));
    } else if (view.container.querySelector(".exam-questions select")) fireEvent.change(view.container.querySelector(".exam-questions select")!, { target: { value: response } });
    else if (view.container.querySelector("input[type=radio]")) fireEvent.click(view.container.querySelector("input[type=radio]")!);
    else fireEvent.change(screen.getByRole("textbox"), { target: { value: response } });
    await act(async () => { await vi.advanceTimersByTimeAsync(450); });
    expect(saveAnswer).toHaveBeenCalledExactlyOnceWith(data.attempt.attempt_id, question.id, response, 0);
    expect(screen.getAllByRole("button", { name: /Go to question/ }).length).toBe(Array.isArray(response) ? 2 : 1);
  });
});

it("keeps draft answers, timer and divider width across passage and mobile-panel switches", () => {
  const contract = contracts.find(case_ => case_.group.question_type === "short_answer")!;
  const data = payload(contract);
  data.passages.push({ ...data.passages[0], id: "66666666-6666-4666-8666-666666666666", order_index: 1, title: "Another fictional passage", question_groups: [] });
  rememberAttemptPresentation(data.attempt, "PRACTICE");
  const view = render(<ReadingRunner initial={data} />);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Latest draft" } });
  const divider = screen.getByRole("separator");
  fireEvent.keyDown(divider, { key: "ArrowRight", shiftKey: true });
  const timer = view.container.querySelector(".exam-timer")!.textContent;
  const input = screen.getByRole("textbox");
  fireEvent.click(screen.getByRole("button", { name: "Questions" }));
  fireEvent.click(screen.getByRole("button", { name: "Passage" }));
  expect(screen.getByRole("textbox")).toBe(input);
  expect(input).toHaveValue("Latest draft");
  fireEvent.click(screen.getByRole("button", { name: "Passage 2" }));
  fireEvent.click(screen.getByRole("button", { name: "Passage 1" }));
  expect(screen.getByRole("textbox")).toHaveValue("Latest draft");
  expect(screen.getByRole("separator")).toBe(divider);
  expect(divider).toHaveAttribute("aria-valuenow", "60");
  expect(view.container.querySelector(".exam-timer")!.textContent).toBe(timer);
});

it("keeps focus in Practice personalization controls when the runner clock ticks", async () => {
  const data = payload(contracts.find(case_ => case_.group.question_type === "short_answer")!, "LISTENING");
  rememberAttemptPresentation(data.attempt, "PRACTICE");
  render(<ListeningRunner initial={data} />);
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  const color = screen.getByRole("button", { name: "Blue" });
  color.focus();
  expect(color).toHaveFocus();
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(color).toHaveFocus();
});

it.each(["PRACTICE", "EXAM"] as const)("Listening %s keeps server audio restrictions and visual image/answer layout", presentation => {
  const data = payload(contracts.find(case_ => case_.group.question_type === "map_labelling")!, "LISTENING");
  data.listening_audio_asset = { id: "77777777-7777-4777-8777-777777777777", original_name: "fictional.mp3", mime_type: "audio/mpeg", file_size: 20, content_url: "/assets/fictional.mp3" };
  rememberAttemptPresentation(data.attempt, presentation);
  const view = render(<ListeningRunner initial={data} />);
  expect(view.container.querySelector(".exam-runner")).toHaveAttribute("data-presentation", presentation);
  expect(view.container.querySelector(".listening-visual-layout")).toBeInTheDocument();
  expect(view.container.querySelector(".listening-visual-answer-pane select")).toBeInTheDocument();
  expect(screen.getByRole("slider", { name: "Audio seek" })).toBeDisabled();
  expect(screen.getByRole("combobox", { name: "Playback speed" })).toBeDisabled();
});

it.each(["READING", "LISTENING"] as const)("uses the chosen Practice presentation for Full Mock %s", module => {
  const data = payload(contracts[0], module);
  data.attempt.test_session_id = "mock-session";
  data.attempt.attempt_context = "FULL_MOCK";
  rememberSessionPresentation("mock-session", "PRACTICE");
  const Runner = module === "READING" ? ReadingRunner : ListeningRunner;
  const view = render(<Runner initial={data} />);
  expect(view.container.querySelector(".exam-runner")).toHaveAttribute("data-presentation", "PRACTICE");
  expect(screen.queryByRole("separator") !== null).toBe(module === "READING");
  expect(screen.getAllByRole("complementary", { name: "Practice tools" }).length).toBeGreaterThan(0);
});

it("keeps Full Mock Listening audio restrictions in the Practice presentation", () => {
  const data = payload(contracts[0], "LISTENING");
  data.attempt.test_session_id = "mock-session";
  data.attempt.attempt_context = "FULL_MOCK";
  data.listening_audio_asset = { id: "77777777-7777-4777-8777-777777777777", original_name: "fictional.mp3", mime_type: "audio/mpeg", file_size: 20, content_url: "/assets/fictional.mp3" };
  rememberSessionPresentation("mock-session", "PRACTICE");
  const view = render(<ListeningRunner initial={data} />);
  expect(view.container.querySelector(".exam-runner")).toHaveAttribute("data-presentation", "PRACTICE");
  expect(screen.getByRole("slider", { name: "Audio seek" })).toBeDisabled();
  expect(screen.getByRole("combobox", { name: "Playback speed" })).toBeDisabled();
});

it.each(["PRACTICE", "EXAM"] as const)("Listening %s preserves section navigation while arranging its groups and flag actions", async presentation => {
  const data = payload(contracts.find(case_ => case_.group.question_type === "short_answer")!, "LISTENING");
  const firstGroup = data.listening_parts[0].question_groups[0];
  const secondQuestion = { ...firstGroup.questions[0], id: "88888888-8888-4888-8888-888888888888", number: 2, prompt: "Second fictional prompt" };
  data.listening_parts[0].question_groups.push({ ...firstGroup, id: "99999999-9999-4999-8999-999999999999", order_index: 1, questions: [secondQuestion] });
  data.listening_parts.push({ ...data.listening_parts[0], id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", order_index: 1, title: "Another fictional section", question_groups: [{ ...firstGroup, id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", questions: [{ ...firstGroup.questions[0], id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", number: 3 }] }] });
  rememberAttemptPresentation(data.attempt, presentation);
  const view = render(<ListeningRunner initial={data} />);
  expect(screen.getAllByRole("textbox")).toHaveLength(presentation === "PRACTICE" ? 2 : 1);
  const flags = screen.getAllByRole("button", { name: /Flag question/ });
  expect(flags).toHaveLength(presentation === "PRACTICE" ? 1 : 3);
  const body = view.container.querySelector(".listening-attempt-body")!;
  const navigation = view.container.querySelector(".listening-navigation-rail")!;
  expect(body.contains(navigation)).toBe(presentation === "EXAM");
  fireEvent.click(screen.getByRole("button", { name: "Section 2" }));
  expect(screen.getByRole("heading", { name: "Another fictional section" })).toBeInTheDocument();
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Latest section answer" } });
  await act(async () => { await vi.advanceTimersByTimeAsync(450); });
  expect(saveAnswer).toHaveBeenCalledExactlyOnceWith(data.attempt.attempt_id, "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "Latest section answer", 0);
});
