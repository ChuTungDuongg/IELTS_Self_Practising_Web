import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { PausedAttemptGate } from "@/features/exam/paused-attempt-gate";
import { accuracyLabel } from "@/features/exam/focused-attempt";
import { resumeAttempt, type AttemptResponse } from "@/lib/api/attempts";
import type { ExamPayload } from "@/lib/api/exam";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/attempts")>(), resumeAttempt: vi.fn(),
}));
const id = "11111111-1111-4111-8111-111111111111";
const attempt: AttemptResponse = {
  attempt_id: id, test_version_id: id, module: "READING", status: "SUBMITTED", finished_reason: "MANUAL_SUBMIT",
  scope: "FOCUSED_UNIT", focused_unit: { kind: "READING_PASSAGE", id, label: "Passage 2", order_index: 1, title: "Fictional parks" },
  timer_mode: "COUNTDOWN", timer_limit_seconds: 1200, started_at: "2026-10-10T00:00:00Z", paused_at: null, total_paused_seconds: 0,
  deadline_at: null, last_active_at: "2026-10-10T00:00:00Z", finished_at: "2026-10-10T00:10:00Z", elapsed_seconds: 600,
  remaining_seconds: 600, raw_score: 10, max_score: 13, band_score: null, server_time: "2026-10-10T00:10:00Z",
};
const passage = { id, order_index: 1, title: "Fictional parks", blocks: [{ id, type: "paragraph" as const, label: "A", text: "Fictional park passage." }],
  question_groups: [{ id, question_type: "short_answer", instruction: "Answer briefly.", config: {}, order_index: 0,
    questions: [{ id, number: 14, prompt: "Fictional question?", config: { max_words: 2, max_numbers: 0 }, answer_key: { kind: "TEXT", accepted: ["parks"] }, explanation: null, order_index: 0 }] }] };

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

it("reviews only the selected passage with raw score and accuracy, without an IELTS band", () => {
  render(<ReadingReviewView data={{ review: { attempt, test_title: "Fictional test", answers: [] }, passages: [passage], highlights: [] }} />);
  expect(screen.getByText("Focused practice · Reading")).toBeInTheDocument();
  expect(screen.getByText("Passage 2 · Fictional parks")).toBeInTheDocument();
  expect(screen.getByText("10 / 13")).toBeInTheDocument();
  expect(screen.getByText("76.9% accuracy")).toBeInTheDocument();
  expect(screen.queryByText(/Band|Official band unavailable/)).not.toBeInTheDocument();
  expect(within(screen.getByLabelText("Review passages")).getAllByRole("button")).toHaveLength(1);
  expect(screen.getByText("Question 14")).toBeInTheDocument();
  expect(screen.queryByText("Question 1")).not.toBeInTheDocument();
});

it.each(["COUNTDOWN", "COUNT_UP"] as const)("preserves focused paused context and %s timing/resume", async (mode) => {
  vi.mocked(resumeAttempt).mockResolvedValue(attempt);
  const exam: ExamPayload = { attempt: { ...attempt, status: "PAUSED", timer_mode: mode }, test_title: "Fictional test", passages: [], writing_tasks: [], listening_parts: [], listening_audio_asset: null, highlights: [] };
  render(<PausedAttemptGate exam={exam} />);
  expect(screen.getByText("Reading · Passage 2")).toBeInTheDocument();
  expect(screen.getByText("Focused practice · Paused")).toBeInTheDocument();
  expect(screen.getByText(mode === "COUNTDOWN" ? "Remaining: 10:00" : "Practice time: 10:00")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Resume attempt" }));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
  expect(resumeAttempt).toHaveBeenCalledWith(id);
  expect(screen.getByRole("link", { name: "Back to history" })).toHaveAttribute("href", "/history");
});

it("does not invent accuracy with a missing or zero maximum", () => {
  expect(accuracyLabel(0, 0)).toBeNull();
  expect(accuracyLabel(null, 13)).toBeNull();
});
