import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { TeacherResultView } from "@/features/classrooms/teacher-result-view";
import { AssignmentList } from "@/features/classrooms/assignment-list";
import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { getHistory, type HistoryItem } from "@/lib/api/history";
import { getAssignmentResult } from "@/lib/api/classroom-results";
import { analyticsSchema, getAnalytics } from "@/lib/api/analytics";
import { startAssignment, type ClassroomAssignment } from "@/lib/api/classrooms";
import { attemptResponseSchema } from "@/lib/api/attempts";
import { apiRequest } from "@/lib/api/client";
import * as speakingApi from "@/lib/api/speaking";
import * as transcriptApi from "@/lib/api/speaking-transcript";
import * as aiApi from "@/lib/api/speaking-ai";
import { sessionPresentationStorageKey } from "@/features/exam/attempt-presentation";

const push = vi.fn(); const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/lib/api/client", async (original) => ({ ...await original<object>(), apiRequest: vi.fn() }));
vi.mock("@/lib/api/speaking", async (original) => ({ ...await original<typeof import("@/lib/api/speaking")>(), fetchSpeakingAudio: vi.fn() }));
vi.mock("@/lib/api/speaking-transcript", async (original) => ({ ...await original<typeof import("@/lib/api/speaking-transcript")>(), latestTranscriptRun: vi.fn(), createTranscriptRun: vi.fn() }));
vi.mock("@/lib/api/speaking-ai", async (original) => ({ ...await original<typeof import("@/lib/api/speaking-ai")>(), latestSpeakingAIRun: vi.fn(), createSpeakingAIRun: vi.fn(), cancelSpeakingAIRun: vi.fn() }));
vi.mock("@/lib/api/analytics", async (original) => ({ ...await original<typeof import("@/lib/api/analytics")>(), getAnalytics: vi.fn() }));
const id = (digit: number) => `${digit}${"1".repeat(7)}-1111-4111-8111-${"1".repeat(12)}`;
const time = "2026-10-12T00:00:00Z";
const summary = { transcript_status: "COMPLETED", ai_status: "COMPLETED", advisory_overall_band: 6.5, ai_run_id: id(8) };
const speaking = { attempt_id: id(1), test_id: id(2), test_version_id: id(3), test_title: "Fictional Speaking history", version_number: 1, module: "SPEAKING", status: "SUBMITTED", started_at: time, finished_at: time, elapsed_seconds: 90, timer_mode: "COUNT_UP", timer_limit_seconds: null, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, speaking_summary: summary } as HistoryItem;
const group = { test_id: speaking.test_id, test_version_id: speaking.test_version_id, test_title: speaking.test_title, version_number: 1, reading: null, listening: null, writing: null, speaking, overall_band_score: null };
const mock = { session_id: id(4), test_version_id: id(3), test_title: speaking.test_title, version_number: 1, status: "COMPLETED", started_at: time, finished_at: time, reading: null, listening: null, writing: null, speaking, overall_band_score: null, module_order: ["LISTENING", "READING", "WRITING", "SPEAKING"] };
const criterion: aiApi.SpeakingAIRun["criteria"]["fc"] = { status: "COMPLETED", score: 6.5, feedback_status: "READY", feedback: "Fictional criterion feedback", strengths: [], improvements: [], evidence_summary: { response_count: 1 }, error_code: null };
const aiRun: aiApi.SpeakingAIRun = { run_id: id(8), attempt_id: id(1), cache_key: "fixture", created_at: time, status: "COMPLETED", stage: "COMPLETED", last_sequence: 9, advisory: true, raw_mean: 6.5, overall_band: 6.5, criteria: { fc: criterion, lr: criterion, gra: criterion, pr: criterion }, summary: { responses: [] }, error_code: null };
const attempt = attemptResponseSchema.parse({ ...speaking, finished_reason: "USER_SUBMIT", paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: time, server_time: time });
const review: speakingApi.SpeakingReviewData = { attempt_id: attempt.attempt_id, test_title: "Fictional assignment Speaking", can_generate_transcript: true, parts: [{ part_number: 1, responses: [{ prompt: { id: id(5), order_index: 0, prompt_type: "SHORT_ANSWER", prompt_text: "Fictional assigned question", preparation_seconds: 0, response_seconds: 60, config_json: {}, part_number: 1, part_title: null, instructions: null }, response: { id: id(6), prompt_id: id(5), active_take_number: 1, started_at: time, completed_at: time, duration_ms: 90000, status: "COMPLETED", completion_reason: "USER_DONE", locked: true, committed_audio_fingerprint: "fixture-audio" }, segments: [{ id: id(7), segment_index: 0, mime_type: "audio/webm", chunk_count: 1, closed_at: time, chunks: [{ id: id(9), sequence: 0, sha256: "fixture", byte_size: 5 }], content_url: `/speaking-attempts/${attempt.attempt_id}/segments/${id(7)}/content` }] }] }] };
const detail = { student_id: id(2), student_display_name: "Fictional assignment student", attempt, session_id: null, reading_review: null, listening_review: null, writing_review: null, ai_runs: [], submitted_answers: [], writing_responses: [], speaking_review: review, speaking_ai_run: aiRun };
const analytics = { total_finalized_attempts: 1, total_active_seconds: 90, average_attempt_seconds: 90, bands: { SPEAKING: { latest: 7, best: 7, average: 7 } }, completed_full_mocks: 1, latest_project_overall: null, latest_full_mock: { session_id: id(4), test_title: "Fictional mock", finished_at: time, reading_band: 7, listening_band: 7, writing_band: 7, speaking_band: null, overall_band: null, module_order: ["LISTENING", "READING", "WRITING", "SPEAKING"] }, trends: [], question_types: [], weak_areas: [], attempts: [], content_timing: [] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(transcriptApi.latestTranscriptRun).mockResolvedValue(null); vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue(null); vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:fixture", revokeObjectURL: vi.fn() }); });
afterEach(() => vi.unstubAllGlobals());
it("keeps Speaking official scores separate from advisory results in all history groupings", async () => {
  const request = vi.fn().mockResolvedValue({ items: [speaking], groups: [group], sessions: [mock], total: 1 });
  const history = await getHistory(request); render(<AttemptHistoryList initialHistory={history} />);
  expect(screen.getByTestId(`history-score-${speaking.attempt_id}`)).toHaveTextContent("Not graded"); expect(screen.getByText("AI advisory band 6.5")).toBeInTheDocument(); expect(screen.getByText("Transcript: Ready")).toBeInTheDocument(); expect(screen.getByRole("link", { name: "Review" })).toHaveAttribute("href", `/review/${speaking.attempt_id}`);
  fireEvent.click(screen.getByRole("tab", { name: "By test" })); expect(screen.getByRole("link", { name: "Review Speaking" })).toHaveAttribute("href", `/review/${speaking.attempt_id}`); expect(screen.getByText("Overall band —")).toBeInTheDocument(); expect(screen.getByText("AI advisory band 6.5")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "By mock test" })); expect(screen.getByRole("link", { name: "Review Speaking" })).toBeInTheDocument(); expect(screen.getByText("Overall band —")).toBeInTheDocument(); expect(screen.queryByText("Overall band 6.5")).toBeNull();
});
it("keeps legacy three-skill Full Mock history readable with its stored overall", async () => {
  const legacy = { ...mock, speaking: undefined, module_order: undefined };
  const history = await getHistory(vi.fn().mockResolvedValue({ items: [], groups: [], sessions: [{ ...legacy, overall_band_score: 7 }], total: 0 })); render(<AttemptHistoryList initialHistory={history} />); fireEvent.click(screen.getByRole("tab", { name: "By mock test" }));
  expect(screen.getByText("Overall band 7.0")).toBeInTheDocument(); expect(screen.queryByText("Speaking")).toBeNull();
});
it("keeps retained assignment Speaking and Full Mock visible without offering deletion", async () => {
  const retained = { ...speaking, deletion_allowed: false };
  const child = { ...retained, attempt_id: id(6), test_title: "Retained assignment mock Speaking", test_session_id: mock.session_id };
  const history = await getHistory(vi.fn().mockResolvedValue({ items: [retained, child], groups: [{ ...group, speaking: retained }], sessions: [{ ...mock, speaking: child, deletion_allowed: false }], total: 2 }));
  render(<AttemptHistoryList initialHistory={history} />);
  expect(screen.getAllByRole("link", { name: "Review" }).map((link) => link.getAttribute("href"))).toContain(`/review/${retained.attempt_id}`);
  expect(screen.queryByRole("button", { name: `Delete ${retained.test_title}` })).toBeNull(); expect(screen.getByText("Retained assignment mock Speaking")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "By test" })); expect(screen.getByRole("link", { name: "Review Speaking" })).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Delete test history" })).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "By mock test" })); expect(screen.getByRole("link", { name: "Review Speaking" })).toHaveAttribute("href", `/review/${child.attempt_id}`); expect(screen.queryByRole("button", { name: "Delete Full Mock" })).toBeNull(); expect(apiRequest).not.toHaveBeenCalled();
});
it("bulk deletion acknowledgement removes personal skills while preserving retained Speaking before refresh", async () => {
  const retained = { ...speaking, deletion_allowed: false };
  const reading = { ...speaking, attempt_id: id(5), test_title: "Fictional deletable Reading", module: "READING", band_score: 7, raw_score: 30, max_score: 40, speaking_summary: null, deletion_allowed: true };
  const history = await getHistory(vi.fn().mockResolvedValue({ items: [reading, retained], groups: [{ ...group, reading, speaking: retained, overall_band_score: 7 }], sessions: [], total: 2 }));
  vi.mocked(apiRequest).mockResolvedValue(undefined); render(<AttemptHistoryList initialHistory={history} />); fireEvent.click(screen.getByRole("tab", { name: "By test" }));
  expect(screen.getByRole("link", { name: "Review Reading" })).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Delete test history" }));
  const dialog = screen.getByRole("dialog"); expect(dialog).toHaveTextContent("Retained assignment work is kept"); fireEvent.click(within(dialog).getByRole("button", { name: "Delete history" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce()); expect(apiRequest).toHaveBeenCalledExactlyOnceWith(`/history/test-versions/${speaking.test_version_id}/standalone-attempts`, { method: "DELETE" });
  expect(screen.getByRole("link", { name: "Review Speaking" })).toBeInTheDocument(); expect(screen.queryByRole("link", { name: "Review Reading" })).toBeNull(); expect(screen.queryByText("Reading")).toBeNull(); expect(screen.queryByRole("button", { name: "Delete test history" })).toBeNull(); expect(screen.getByText("Overall band —")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "By skill" })); expect(screen.getByText(retained.test_title)).toBeInTheDocument(); expect(screen.queryByText(reading.test_title)).toBeNull(); expect(screen.queryByRole("button", { name: `Delete ${retained.test_title}` })).toBeNull();
});
it("parses provenance-scoped classroom Speaking data and renders only read-only review actions", async () => {
  const request = vi.fn().mockResolvedValue(detail); const parsed = await getAssignmentResult(id(2), id(3), id(1), request);
  expect(request).toHaveBeenCalledExactlyOnceWith(`/classrooms/${id(2)}/assignments/${id(3)}/attempts/${id(1)}`); expect(parsed.speaking_ai_run?.advisory).toBe(true);
  vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue(aiRun); vi.mocked(transcriptApi.latestTranscriptRun).mockResolvedValue({ run_id: id(8), attempt_id: id(1), cache_key: "fixture", status: "COMPLETED", last_sequence: 1, created_at: time, responses: [{ response_id: id(6), status: "READY", verbatim: "Fictional assigned transcript", clean: "Fictional assigned transcript", words: [], error_code: null, source_audio_fingerprint: "fixture-audio" }] }); vi.mocked(speakingApi.fetchSpeakingAudio).mockResolvedValue(new Blob(["audio"]));
  render(<TeacherResultView data={parsed} />); expect(await screen.findByText("Fictional assigned transcript")).toBeInTheDocument(); expect(screen.getByRole("heading", { name: "Advisory Overall Speaking Band" })).toBeInTheDocument();
  fireEvent.click(screen.getByText("Fictional assigned question")); fireEvent.click(screen.getByRole("button", { name: "Load recording" })); expect(await screen.findByLabelText("Recording segment 1")).toHaveAttribute("src", "blob:fixture");
  expect(screen.queryByRole("button", { name: /Generate Transcript|Grade with AI|Stop grading|Retry recording|Start Speaking/ })).toBeNull(); expect(transcriptApi.createTranscriptRun).not.toHaveBeenCalled(); expect(aiApi.createSpeakingAIRun).not.toHaveBeenCalled(); expect(aiApi.cancelSpeakingAIRun).not.toHaveBeenCalled();
});
it("does not invent a Speaking review for locked or unavailable assignment work", async () => {
  const parsed = await getAssignmentResult(id(2), id(3), id(1), vi.fn().mockResolvedValue({ ...detail, speaking_review: null, speaking_ai_run: null })); render(<TeacherResultView data={parsed} />); await act(async () => undefined);
  expect(screen.queryByText("Fictional assigned question")).toBeNull(); expect(aiApi.latestSpeakingAIRun).not.toHaveBeenCalled(); expect(transcriptApi.latestTranscriptRun).not.toHaveBeenCalled();
});
it("offers Speaking analytics using only official band summaries", async () => {
  vi.mocked(getAnalytics).mockResolvedValue(analyticsSchema.parse(analytics)); render(<AnalyticsDashboardView initial={analyticsSchema.parse(analytics)} />);
  expect(screen.getByText("Speaking latest / best / average").parentElement).toHaveTextContent("7.0 / 7.0 / 7.00"); fireEvent.click(screen.getByRole("button", { name: "Speaking" })); await waitFor(() => expect(getAnalytics).toHaveBeenCalledExactlyOnceWith("SPEAKING")); expect(screen.getByText("Latest overall").parentElement).toHaveTextContent("—");
});
it("starts assigned Speaking through assignment provenance instead of personal practice", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ attempt_id: id(1), test_session_id: null });
  const assignment = { id: id(4), classroom_id: id(2), test_version_id: id(3), title: "Fictional Speaking assignment", note: null, status: "ACTIVE", version: { test_title: "Fictional assigned version", modules: [{ module_type: "SPEAKING", recommended_duration_seconds: 900 }] } } as unknown as ClassroomAssignment;
  render(<AssignmentList assignments={[assignment]} />); expect(screen.getByRole("option", { name: "Speaking" })).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Start assignment" }));
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith(`/attempt/${id(1)}`));
  expect(apiRequest).toHaveBeenCalledExactlyOnceWith(`/classroom-assignments/${id(4)}/start`, { method: "POST", body: expect.any(String) });
  expect(JSON.parse(vi.mocked(apiRequest).mock.calls[0][1]!.body as string)).toEqual({ mode: "MODULE", module: "SPEAKING", scope: "FULL_MODULE", speaking_mode: "EXAM", timer: { mode: "COUNT_UP" } });
});
it("accepts typed focused Speaking assignment practice without losing assignment identity", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ attempt_id: id(1), test_session_id: null });
  await startAssignment(id(4), { mode: "MODULE", module: "SPEAKING", scope: "FOCUSED_UNIT", focused_unit: { kind: "SPEAKING_PROMPT", id: id(5) }, speaking_mode: "PRACTICE", timer: { mode: "COUNT_UP" } });
  expect(apiRequest).toHaveBeenCalledWith(`/classroom-assignments/${id(4)}/start`, expect.objectContaining({ method: "POST" })); expect(JSON.parse(vi.mocked(apiRequest).mock.calls[0][1]!.body as string)).toMatchObject({ focused_unit: { kind: "SPEAKING_PROMPT", id: id(5) }, speaking_mode: "PRACTICE" });
});
it("requires all four configured skills before offering assignment Full Mock", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ attempt_id: null, test_session_id: id(7) });
  const assignment = { id: id(4), classroom_id: id(2), test_version_id: id(3), title: "Fictional mock assignment", note: null, status: "ACTIVE", version: { test_title: "Fictional mock", modules: ["LISTENING", "READING", "WRITING"].map((module_type) => ({ module_type, recommended_duration_seconds: 3600 })) } } as unknown as ClassroomAssignment;
  const view = render(<AssignmentList assignments={[assignment]} />); expect(screen.queryByRole("option", { name: "Full Mock" })).toBeNull();
  view.rerender(<AssignmentList assignments={[{ ...assignment, version: { ...assignment.version!, modules: [...assignment.version!.modules, { ...assignment.version!.modules[0], module_type: "SPEAKING", recommended_duration_seconds: 900 }] } }]} />);
  expect(screen.getByRole("option", { name: "Full Mock" })).toBeInTheDocument(); fireEvent.change(screen.getByRole("combobox", { name: "Practice mode" }), { target: { value: "FULL_MOCK" } }); fireEvent.click(screen.getByRole("button", { name: "Start assignment" }));
  expect(apiRequest).not.toHaveBeenCalled();
  expect(screen.getByRole("radio", { name: "Practice" })).toBeChecked();
  fireEvent.click(screen.getByRole("radio", { name: "Legacy" }));
  fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith(`/test-session/${id(7)}`)); expect(JSON.parse(vi.mocked(apiRequest).mock.calls[0][1]!.body as string)).toEqual({ mode: "FULL_MOCK" });
  expect(localStorage.getItem(sessionPresentationStorageKey(id(7)))).toBe("EXAM");
});

it("shows authorized owning teacher Speaking grading while preserving transcript and audio action restrictions", async () => {
  const grading = { context: "CLASSROOM" as const, can_edit_final: true, can_copy_ai_to_final: true, waiting_for_teacher: false };
  const parsed = await getAssignmentResult(id(2), id(3), id(1), vi.fn().mockResolvedValue({ ...detail, grading, speaking_review: { ...review, grading } }));
  render(<TeacherResultView data={parsed} classroomId={id(2)} assignmentId={id(3)} />);
  expect(screen.getByText("Teacher grading")).toBeInTheDocument();
  expect(screen.getByLabelText("Final FC")).toBeEnabled(); expect(screen.getByRole("button", { name: "Save final score" })).toBeDisabled();
  await screen.findByText("Assessment complete");
  expect(screen.getByRole("button", { name: "Copy AI scores to form" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Generate Transcript|Grade with AI|Stop grading|Retry recording/ })).toBeNull();
  expect(transcriptApi.createTranscriptRun).not.toHaveBeenCalled(); expect(aiApi.createSpeakingAIRun).not.toHaveBeenCalled();
});

it("keeps objective classroom Reading results read-only even in an assignment grading page", async () => {
  const readingAttempt = { ...attempt, module: "READING" };
  const parsed = await getAssignmentResult(id(2), id(3), id(1), vi.fn().mockResolvedValue({ ...detail, attempt: readingAttempt, speaking_review: null, speaking_ai_run: null, reading_review: { review: { attempt: readingAttempt, test_title: "Fictional objective review", answers: [] }, highlights: [], passages: [{ id: id(5), title: "Fictional passage", order_index: 0, blocks: [{ id: id(6), type: "paragraph", text: "Fictional saved passage." }], question_groups: [] }] }, grading: { context: "CLASSROOM", can_edit_final: false, can_copy_ai_to_final: false, waiting_for_teacher: false } }));
  render(<TeacherResultView data={parsed} classroomId={id(2)} assignmentId={id(3)} />);
  expect(screen.getByText("Read-only result")).toBeInTheDocument(); expect(screen.getByText("Fictional saved passage.")).toBeInTheDocument();
  expect(screen.queryByRole("combobox")).toBeNull(); expect(screen.queryByRole("textbox")).toBeNull(); expect(screen.queryByRole("button", { name: /Save final|Save Task|Copy AI/ })).toBeNull();
});
