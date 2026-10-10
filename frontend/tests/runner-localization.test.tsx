import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { WritingRunner } from "@/features/writing/writing-runner";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { WritingReviewView } from "@/features/writing/writing-review";
import { PausedAttemptGate } from "@/features/exam/paused-attempt-gate";
import { TestSessionTransition } from "@/features/exam/test-session-transition";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import { useExamSubmit } from "@/features/exam/use-exam-submit";
import { MatchingRenderer } from "@/features/questions/renderers";
import { SelectableText } from "@/features/highlighting/selectable-text";
import { draftStorageKey } from "@/features/exam/exam-draft-recovery";
import * as attempts from "@/lib/api/attempts";
import * as examApi from "@/lib/api/exam";
import { ApiError } from "@/lib/api/client";
import { advanceTestSession, type TestSession } from "@/lib/api/test-sessions";
import type { BuilderVersion } from "@/lib/api/builder";
import type { ExamGroup } from "@/features/questions/types";
import { useEffect, type ReactElement } from "react";
import { useLocale } from "@/lib/i18n/locale-provider";
import { renderWithLocale as renderLocale } from "./locale-test-utils";

const boundary = vi.hoisted(() => ({ stores: vi.fn(), queues: vi.fn(), push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => boundary }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: null }) }));
vi.mock("@/lib/api/attempts", async (original) => ({ ...await original<typeof attempts>(), getAttempt: vi.fn(), pauseAttempt: vi.fn(), resumeAttempt: vi.fn(), recordActivity: vi.fn(), recordNavigation: vi.fn(), saveAnswer: vi.fn(), saveWritingResponse: vi.fn() }));
vi.mock("@/lib/api/exam", async (original) => ({ ...await original<typeof examApi>(), getExam: vi.fn(), submitAttempt: vi.fn(), saveFlag: vi.fn(), createHighlight: vi.fn(), deleteHighlight: vi.fn(), deleteAllHighlights: vi.fn(), saveWritingTaskScore: vi.fn() }));
vi.mock("@/lib/api/test-sessions", () => ({ advanceTestSession: vi.fn() }));
vi.mock("@/features/exam/exam-draft-recovery", async (original) => {
  const actual = await original<typeof import("@/features/exam/exam-draft-recovery")>();
  return { ...actual, ExamDraftStore: class extends actual.ExamDraftStore {
    constructor(...args: ConstructorParameters<typeof actual.ExamDraftStore>) { super(...args); boundary.stores(...args); }
  } };
});
vi.mock("@/features/exam/revision-autosave", async (original) => {
  const actual = await original<typeof import("@/features/exam/revision-autosave")>();
  const subscribe = actual.RevisionAutosaveQueue.prototype.subscribe;
  vi.spyOn(actual.RevisionAutosaveQueue.prototype, "subscribe").mockImplementation(function (this: InstanceType<typeof actual.RevisionAutosaveQueue>, listener) {
    boundary.queues(this);
    return subscribe.call(this, listener);
  });
  return actual;
});

const id = (n: number) => `11111111-1111-4111-8111-${String(n).padStart(12, "0")}`;
function payload(module: "READING" | "LISTENING" | "WRITING", focused = false): examApi.ExamPayload {
  const now = new Date().toISOString();
  const group = (number: number) => ({ id: id(30 + number), question_type: "short_answer", instruction: "Authored instruction: answer briefly.", config: {}, order_index: 0,
    questions: [{ id: id(40 + number), number, prompt: "Authored question stays exact.", config: { max_words: 2 }, order_index: 0, value: "original", flagged: true, answer_revision: 3 }] });
  const units = [0, 1].map((order_index) => ({ id: id(10 + order_index), title: "Section 2", order_index, question_groups: [group(order_index + 1)] }));
  const attempt: attempts.AttemptResponse = { attempt_id: id(1), test_version_id: id(2), module, scope: focused ? "FOCUSED_UNIT" : "FULL_MODULE", attempt_context: "STANDALONE",
    focused_unit: focused ? { kind: module === "READING" ? "READING_PASSAGE" : module === "LISTENING" ? "LISTENING_PART" : "WRITING_TASK", id: id(10), order_index: 0, label: "Section 1", title: "Section 2" } : null,
    status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: now, paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: now, finished_at: null,
    elapsed_seconds: 120, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: now };
  return { attempt, test_title: "Authored test title", passages: module === "READING" ? units.map((unit) => ({ ...unit, blocks: [{ id: id(60 + unit.order_index), type: "paragraph", label: "A", text: "Fictional authored passage." }] })) : [],
    listening_parts: module === "LISTENING" ? units.map((unit) => ({ ...unit, audio_start_seconds: 10, audio_end_seconds: 40 })) : [],
    listening_audio_asset: module === "LISTENING" ? { id: id(70), original_name: "authored.mp3", mime_type: "audio/mpeg", file_size: 100, content_url: "/assets/fictional" } : null,
    audio_policy: { allow_seeking: true, allow_speed: true },
    writing_tasks: module === "WRITING" ? units.map((unit) => ({ id: unit.id, task_number: unit.order_index + 1, order_index: unit.order_index, prompt: "Fictional authored Writing prompt.", image_asset_id: null, image_asset: null, minimum_recommended_words: 150, recommended_duration_seconds: 1200, content: "Original Writing response", word_count: 3, response_revision: 3 })) : [],
    highlights: module === "WRITING" ? [] : [{ id: id(80), target_kind: "QUESTION_PROMPT", target_id: id(41), start_offset: 0, end_offset: 8, selected_text: "Authored", created_at: now }] };
}
const requestSpies = () => [attempts.saveAnswer, attempts.saveWritingResponse, attempts.recordActivity, attempts.recordNavigation, attempts.getAttempt, attempts.pauseAttempt, attempts.resumeAttempt, examApi.getExam, examApi.submitAttempt, examApi.saveFlag, examApi.createHighlight, examApi.deleteHighlight, examApi.deleteAllHighlights, boundary.push, boundary.refresh, boundary.replace];
function snapshotRequests() { return requestSpies().map((spy) => structuredClone(vi.mocked(spy).mock.calls)); }
let changeLocale: (locale: "en" | "vi") => void;
function LocaleDriver() { const { setLocale } = useLocale(); useEffect(() => { changeLocale = setLocale; }, [setLocale]); return null; }
function renderWithLocale(ui: ReactElement) { return renderLocale(<>{ui}<LocaleDriver /></>); }
// Attempts have no language widget. Change the provider directly so a synthetic
// outside click does not count as exam activity through the existing window listener.
function switchLocale(locale: "en" | "vi") { act(() => changeLocale(locale)); }

beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-11T00:00:00Z")); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: vi.fn() });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
  Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
  Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: vi.fn() });
  vi.mocked(attempts.recordActivity).mockResolvedValue({} as never);
  vi.mocked(attempts.recordNavigation).mockResolvedValue(undefined);
  vi.mocked(examApi.saveFlag).mockResolvedValue(undefined);
  vi.mocked(attempts.saveAnswer).mockImplementation(async (_attempt, question_id, value, revision) => ({ question_id, value, revision: revision + 1, is_correct: null, saved_at: new Date().toISOString() }));
  vi.mocked(attempts.saveWritingResponse).mockImplementation(async (_attempt, writing_task_id, content, revision) => ({ writing_task_id, content, revision: revision + 1, word_count: 3, saved_at: new Date().toISOString() }));
});
afterEach(() => vi.useRealTimers());

it.each((["READING", "LISTENING", "WRITING"] as const).flatMap((module) => [false, true].map((focused) => ({ module, focused }))))("locale switch preserves real $module focused=$focused runner, draft store, pending save, timer and requests", async ({ module, focused }) => {
  const data = payload(module, focused);
  if (focused) { data.passages = data.passages.slice(0, 1); data.listening_parts = data.listening_parts.slice(0, 1); data.writing_tasks = data.writing_tasks.slice(0, 1); }
  const Runner = module === "READING" ? ReadingRunner : module === "LISTENING" ? ListeningRunner : WritingRunner;
  const view = renderWithLocale(<Runner initial={data} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  // Change units before editing, so the identity assertions exercise a non-default selection.
  if (!focused) {
    if (module === "WRITING") fireEvent.click(screen.getByRole("tab", { name: /^Task 2/ }));
    else fireEvent.click(screen.getByRole("button", { name: module === "READING" ? "Passage 2" : "Section 2" }));
  }
  if (module !== "WRITING") {
    fireEvent.click(screen.getByRole("button", { name: `Unflag question ${focused ? 1 : 2}` }));
    fireEvent.click(screen.getByRole("button", { name: `Flag question ${focused ? 1 : 2}` }));
  }
  const input = screen.getByRole("textbox") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "Untranslated learner draft" } });
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  // A second edit is still pending when locale changes.
  fireEvent.change(input, { target: { value: "Untranslated latest draft" } });
  const runner = view.container.querySelector(".exam-runner");
  const timer = view.container.querySelector(".exam-timer")!.textContent!.match(/\d+:\d+$/)![0];
  const storage = sessionStorage.getItem(draftStorageKey(data.attempt.attempt_id));
  const reconcileCount = boundary.stores.mock.calls.length;
  const queues = boundary.queues.mock.calls.length;
  expect(reconcileCount).toBe(1); expect(queues).toBe(1);
  const mark = view.container.querySelector("mark");
  const audio = view.container.querySelector("audio");
  if (audio) { Object.defineProperty(audio, "duration", { configurable: true, value: 100 }); fireEvent.loadedMetadata(audio); audio.currentTime = 25; audio.playbackRate = 1.5; audio.volume = 0.35; audio.muted = true; fireEvent.timeUpdate(audio); }
  const media = [HTMLMediaElement.prototype.play, HTMLMediaElement.prototype.pause, HTMLMediaElement.prototype.load].map((fn) => vi.mocked(fn).mock.calls.length);
  const requests = snapshotRequests();
  for (const locale of ["vi", "en"] as const) {
    switchLocale(locale);
    expect(screen.getByRole("button", { name: locale === "vi" ? "Tạm dừng và thoát" : "Pause & exit" })).toBeInTheDocument();
    expect(view.container.querySelector(".exam-runner")).toBe(runner);
    expect(screen.getByRole("textbox")).toBe(input);
    expect(input).toHaveValue("Untranslated latest draft");
    expect(view.container.querySelector(".exam-timer")!.textContent).toMatch(new RegExp(`${timer}$`));
    expect(boundary.stores).toHaveBeenCalledTimes(reconcileCount);
    expect(boundary.queues).toHaveBeenCalledTimes(queues);
    expect(snapshotRequests()).toEqual(requests);
    expect(sessionStorage.getItem(draftStorageKey(data.attempt.attempt_id))).toBe(storage);
    expect(screen.getByRole("heading", { name: "Authored test title" })).toBeInTheDocument();
    if (module === "WRITING") { expect(screen.getByText("Fictional authored Writing prompt.")).toBeInTheDocument(); if (!focused) expect(screen.getByRole("tab", { selected: true })).toHaveTextContent(locale === "vi" ? "Bài viết 2" : "Task 2"); }
    else {
      expect(input.closest(".exam-question-target")).toHaveTextContent("Authored question stays exact.");
      expect(screen.getByRole("button", { name: `${locale === "vi" ? "Bỏ đánh dấu câu hỏi" : "Unflag question"} ${focused ? 1 : 2}` })).toHaveAttribute("aria-pressed", "true");
      expect(view.container.querySelector("mark")).toBe(mark);
      if (mark) expect(mark).toHaveTextContent("Authored");
    }
    if (audio) { expect(view.container.querySelector("audio")).toBe(audio); expect([audio.currentTime, audio.playbackRate, audio.volume, audio.muted]).toEqual([25, 1.5, 0.35, true]); }
    expect([HTMLMediaElement.prototype.play, HTMLMediaElement.prototype.pause, HTMLMediaElement.prototype.load].map((fn) => vi.mocked(fn).mock.calls.length)).toEqual(media);
  }
  await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  const save = module === "WRITING" ? attempts.saveWritingResponse : attempts.saveAnswer;
  expect(save).toHaveBeenLastCalledWith(data.attempt.attempt_id, module === "WRITING" ? id(focused ? 10 : 11) : id(focused ? 41 : 42), "Untranslated latest draft", 4);
});

it("preserves an in-flight autosave worker and revision across locale changes", async () => {
  let finish!: (value: Awaited<ReturnType<typeof attempts.saveAnswer>>) => void;
  vi.mocked(attempts.saveAnswer).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const data = payload("READING"); renderWithLocale(<ReadingRunner initial={data} />);
  fireEvent.change(screen.getByLabelText("Question 1"), { target: { value: "In-flight draft" } });
  await act(async () => { await vi.advanceTimersByTimeAsync(400); });
  expect(attempts.saveAnswer).toHaveBeenCalledExactlyOnceWith(id(1), id(41), "In-flight draft", 3);
  const requests = snapshotRequests(); const stored = sessionStorage.getItem(draftStorageKey(id(1)));
  switchLocale("vi"); expect(screen.getByText("Đang lưu…")).toBeInTheDocument(); expect(snapshotRequests()).toEqual(requests); expect(sessionStorage.getItem(draftStorageKey(id(1)))).toBe(stored);
  await act(async () => { finish({ question_id: id(41), value: "In-flight draft", revision: 4, saved_at: new Date().toISOString(), is_correct: null }); });
  expect(screen.getByLabelText("Câu hỏi 1")).toHaveValue("In-flight draft"); expect(boundary.queues).toHaveBeenCalledTimes(1); expect(boundary.stores).toHaveBeenCalledTimes(1);
});

it.each([true, false])("full Listening keeps whole recording and Full Mock seeking policy allowSeeking=%s", (allowSeeking) => {
  const data = payload("LISTENING"); data.audio_policy = { allow_seeking: allowSeeking, allow_speed: allowSeeking };
  if (!allowSeeking) data.attempt.attempt_context = "FULL_MOCK";
  const view = renderWithLocale(<ListeningRunner initial={data} />); const audio = view.container.querySelector("audio")!;
  Object.defineProperty(audio, "duration", { configurable: true, value: 100 }); fireEvent.loadedMetadata(audio); switchLocale("vi");
  expect(audio.currentTime).toBe(0); expect(screen.getByLabelText("Tua âm thanh")).toHaveAttribute("max", "100");
  expect((screen.getByLabelText("Tua âm thanh") as HTMLInputElement).disabled).toBe(!allowSeeking); expect((screen.getByLabelText("Tốc độ phát") as HTMLSelectElement).disabled).toBe(!allowSeeking);
});

it("localizes submit fallback at presentation without changing the mutation callback or repeating it", async () => {
  const data = payload("READING"); const flush = vi.fn().mockResolvedValue(undefined); const accept = vi.fn(); const stopped = () => false;
  const runMutation = <T,>(mutation: () => Promise<T>) => mutation(); const renders = vi.fn();
  vi.mocked(examApi.submitAttempt).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", 0)); vi.mocked(attempts.getAttempt).mockRejectedValueOnce(new Error("offline"));
  function Probe() { const state = useExamSubmit({ attemptId: id(1), initialAttempt: data.attempt, flush, accept, isStopped: stopped, runMutation }); renders(state.submit); return <><button onClick={() => void state.submit()}>Submit probe</button><p>{state.submitError}</p></>; }
  renderWithLocale(<Probe />); await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Submit probe" })); });
  expect(screen.getByText("We couldn't confirm whether your submission completed. Reconnect and try again.")).toBeInTheDocument(); const submit = renders.mock.lastCall![0]; const requests = snapshotRequests();
  switchLocale("vi"); expect(screen.getByText("Chưa xác nhận được bài đã nộp thành công. Kết nối lại và thử lần nữa.")).toBeInTheDocument(); expect(renders.mock.lastCall![0]).toBe(submit); expect(snapshotRequests()).toEqual(requests); expect(flush).toHaveBeenCalledTimes(1);
});

it.each(["clip", "full", "external"] as const)("focused Listening %s preserves optional playback across EN/VI and review", (mode) => {
  const data = payload("LISTENING", true); data.listening_parts = [data.listening_parts[0]];
  if (mode === "full") { data.listening_parts[0].audio_start_seconds = null; data.listening_parts[0].audio_end_seconds = null; }
  if (mode === "external") data.listening_audio_asset = null;
  const original = JSON.stringify(data);
  const view = renderWithLocale(<ListeningRunner initial={data} />);
  const audio = view.container.querySelector("audio");
  if (audio) { Object.defineProperty(audio, "duration", { configurable: true, value: 100 }); fireEvent.loadedMetadata(audio); }
  switchLocale("vi");
  expect(screen.getByLabelText("Câu hỏi 1")).toHaveValue("original");
  expect(screen.getByRole("heading", { name: "Section 2" })).toBeInTheDocument();
  if (audio) { expect(view.container.querySelector("audio")).toBe(audio); expect(screen.getByLabelText("Tua âm thanh")).toHaveAttribute("max", mode === "clip" ? "30" : "100"); }
  else { expect(view.container.querySelector("audio")).toBeNull(); expect(screen.getByText("Chưa có bản ghi âm đính kèm. Bạn có thể tiếp tục trả lời câu hỏi và dùng bản ghi âm bên ngoài nếu cần.")).toHaveClass("notice"); }
  if (mode === "full") expect(screen.getByText("Chưa cấu hình khoảng âm thanh cho phần này. Bạn có thể nghe toàn bộ bản ghi.")).toHaveClass("notice");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  view.unmount();
  const review: Awaited<ReturnType<typeof examApi.getListeningReview>> = { review: { attempt: { ...data.attempt, status: "SUBMITTED", raw_score: 1, max_score: 2 }, test_title: data.test_title, answers: [] }, highlights: data.highlights, audio_asset: data.listening_audio_asset,
    parts: data.listening_parts.map((part) => ({ ...part, question_groups: part.question_groups.map((group) => ({ ...group, questions: group.questions.map((question) => ({ ...question, answer_key: { accepted: ["Raw key"] }, explanation: "Raw explanation" })) })) })) };
  renderWithLocale(<ListeningReviewView data={review} />);
  expect(screen.getByText("1 / 2")).toBeInTheDocument(); expect(screen.getByText("50.0% chính xác")).toBeInTheDocument();
  expect(screen.queryByText(/Band|Dải điểm/)).not.toBeInTheDocument();
  expect(screen.getByText("Raw explanation")).toBeInTheDocument(); expect(JSON.stringify(data)).toBe(original);
});

it("restores saved VI after mount without recreating actual runner stores or requests", () => {
  localStorage.setItem("ielts-locale", "vi");
  renderWithLocale(<ReadingRunner initial={payload("READING")} />);
  expect(screen.getByRole("button", { name: "Tạm dừng và thoát" })).toBeInTheDocument();
  expect(boundary.stores).toHaveBeenCalledTimes(1); expect(boundary.queues).toHaveBeenCalledTimes(1);
  expect(attempts.recordNavigation).toHaveBeenCalledTimes(2); expect(examApi.getExam).not.toHaveBeenCalled();
});

it("keeps open pause confirmation identity and focus while its labels update", () => {
  renderWithLocale(<ReadingRunner initial={payload("READING")} />);
  fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
  const dialog = screen.getByRole("dialog"); const focused = document.activeElement;
  switchLocale("vi");
  expect(screen.getByRole("dialog", { name: "Tạm dừng bài làm?" })).toBe(dialog); expect(document.activeElement).toBe(focused);
  expect(attempts.pauseAttempt).not.toHaveBeenCalled();
});

it("keeps highlight popover, ID, selected text and focus with unchanged semantic deletion payload", async () => {
  const highlight = payload("READING").highlights[0]; const remove = vi.fn().mockResolvedValue(undefined);
  renderWithLocale(<SelectableText text="Authored question stays exact." target={{ target_kind: "QUESTION_PROMPT", target_id: id(41) }} controller={{ highlights: [highlight], onDelete: remove }} />);
  fireEvent.click(screen.getByRole("button", { name: "Highlight: Authored. Open options" }));
  const dialog = screen.getByRole("dialog"); const button = within(dialog).getByRole("button"); button.focus();
  switchLocale("vi");
  expect(screen.getByRole("dialog", { name: "Tùy chọn tô sáng" })).toBe(dialog); expect(document.activeElement).toBe(button); expect(within(dialog).getByText("Authored", { selector: "q" })).toBeInTheDocument();
  switchLocale("en"); await act(async () => { fireEvent.click(button); }); expect(remove).toHaveBeenCalledExactlyOnceWith(highlight.id);
  expect([highlight.start_offset, highlight.end_offset]).toEqual([0, 8]);
});

it("translates generic selector UI while keeping authored option values and prompt exact", () => {
  const onAnswer = vi.fn(); const group: ExamGroup = { id: id(30), question_type: "matching", instruction: "Raw instructions", config: { options: [{ id: "a", label: "A", text: "Authored option" }] }, order_index: 0,
    questions: [{ id: id(40), number: 2, prompt: "Raw prompt", config: {}, order_index: 0 }] };
  renderWithLocale(<MatchingRenderer group={group} values={{ [id(40)]: "a" }} onAnswer={onAnswer} />);
  const select = screen.getByLabelText("Question 2"); switchLocale("vi");
  expect(screen.getByLabelText("Câu hỏi 2")).toBe(select); expect(select).toHaveValue("a");
  expect(screen.getByRole("option", { name: "Chọn câu trả lời" })).toHaveValue(""); expect(screen.getByRole("option", { name: "A — Authored option" })).toHaveValue("a"); expect(screen.getByText("Raw prompt")).toBeInTheDocument(); expect(onAnswer).not.toHaveBeenCalled();
});

it("localizes paused and Full Mock transition controls without resume/advance requests", () => {
  const data = payload("READING", true); data.attempt.status = "PAUSED";
  const view = renderWithLocale(<PausedAttemptGate exam={data} />); switchLocale("vi");
  expect(screen.getByRole("button", { name: "Tiếp tục bài làm" })).toBeInTheDocument(); expect(screen.getByText("Bài đọc 1 · Section 2")).toBeInTheDocument(); expect(attempts.resumeAttempt).not.toHaveBeenCalled();
  view.unmount();
  const session: TestSession = { session_id: id(90), test_version_id: id(2), test_title: "Raw Full Mock", version_number: 1, status: "IN_PROGRESS", started_at: new Date().toISOString(), finished_at: null, current_module: "WRITING", next_module: "WRITING", current_attempt: null, attempts: [{ attempt_id: id(1), module: "READING", status: "SUBMITTED", band_score: 7, raw_score: 30, max_score: 40, elapsed_seconds: 3600 }], warnings: ["Raw server warning"], overall_band_score: null };
  renderWithLocale(<TestSessionTransition initial={session} />);
  expect(screen.getByRole("button", { name: "Tiếp tục đến Viết" })).toBeInTheDocument(); expect(screen.getByText("Raw server warning")).toBeInTheDocument(); switchLocale("en"); expect(screen.getByRole("button", { name: "Continue to Writing" })).toBeInTheDocument(); expect(advanceTestSession).not.toHaveBeenCalled();
});

it("localizes Reading and Writing review labels while keeping scores, draft and criterion input", () => {
  const reading = payload("READING", true);
  const data: Awaited<ReturnType<typeof examApi.getReadingReview>> = { review: { attempt: { ...reading.attempt, status: "SUBMITTED", raw_score: 1, max_score: 2 }, test_title: reading.test_title, answers: [] }, highlights: reading.highlights,
    passages: reading.passages.map((passage) => ({ ...passage, question_groups: passage.question_groups.map((group) => ({ ...group, questions: group.questions.map((question) => ({ ...question, answer_key: { accepted: ["Raw key"] }, explanation: "Raw explanation" })) })) })) };
  const view = renderWithLocale(<ReadingReviewView data={data} />); switchLocale("vi");
  expect(screen.getByText("50.0% chính xác")).toBeInTheDocument(); expect(screen.getAllByText("Raw explanation")).toHaveLength(1); expect(screen.getByText("Fictional authored passage.")).toBeInTheDocument(); view.unmount();
  const writing = payload("WRITING", true);
  const review: examApi.WritingReviewPayload = { review: { attempt: writing.attempt, test_title: writing.test_title, answers: [], writing_responses: [], highlights: [], flags: [] }, tasks: writing.writing_tasks.slice(0, 1).map((task) => ({ ...task, writing_task_id: task.id, task_number: 3, score: null })), task1_overall: null, task2_overall: null, weighted_overall: null, band_score: null };
  renderWithLocale(<WritingReviewView data={review} />);
  const criterion = screen.getByLabelText("Bài 3 TA", { selector: "select" }); fireEvent.change(criterion, { target: { value: "6.5" } }); switchLocale("en");
  expect(screen.getAllByLabelText("Task 3 TA", { selector: "select" })[0]).toBe(criterion); expect(criterion).toHaveValue("6.5"); expect(screen.getByText("Original Writing response")).toBeInTheDocument(); expect(examApi.saveWritingTaskScore).not.toHaveBeenCalled();
});

it("keeps DraftPreview ephemeral answer and local footer when common controls translate", () => {
  const reading = payload("READING");
  const version = { id: id(2), test_id: id(3), test_title: reading.test_title, version_number: 1, status: "DRAFT", modules: [{ id: id(4), revision: 1, module_type: "READING", title: "Raw title", recommended_duration_seconds: 3600, audio_asset: null, listening_parts: [], writing_tasks: [], passages: reading.passages.map((passage) => ({ ...passage, revision: 1, question_groups: passage.question_groups.map((group) => ({ ...group, revision: 1, questions: group.questions.map((question) => ({ ...question, answer_key: { accepted: ["Raw key"] }, explanation: null })) })) })) }] } as BuilderVersion;
  const view = renderWithLocale(<DraftPreview version={version} moduleType="READING" />); const input = screen.getByLabelText("Question 1"); fireEvent.change(input, { target: { value: "Preview draft" } });
  switchLocale("vi"); expect(screen.getByLabelText("Câu hỏi 1")).toBe(input); expect(input).toHaveValue("Preview draft"); expect(screen.getByRole("link", { name: "Quay lại trình biên soạn" })).toHaveAttribute("href", expect.stringContaining("workspace=reading")); expect(view.container.querySelector(".exam-footer")).toBeInTheDocument(); expect(attempts.saveAnswer).not.toHaveBeenCalled();
});
