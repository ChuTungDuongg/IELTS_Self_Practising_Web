import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { PausedAttemptGate } from "@/features/exam/paused-attempt-gate";
import { resumeAttempt, type AttemptResponse } from "@/lib/api/attempts";
import type { ExamPayload, getListeningReview } from "@/lib/api/exam";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/attempts", () => ({ resumeAttempt: vi.fn() }));
const id = "11111111-1111-4111-8111-111111111111";
const now = new Date().toISOString();
const attempt: AttemptResponse = {
  attempt_id: id, test_version_id: id, module: "LISTENING", scope: "FOCUSED_UNIT", attempt_context: "STANDALONE",
  focused_unit: { kind: "LISTENING_PART", id, order_index: 1, label: "Section 2", title: "Fictional tour" },
  status: "SUBMITTED", finished_reason: "MANUAL", timer_mode: "COUNTDOWN", timer_limit_seconds: 600,
  started_at: now, paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: now, finished_at: now,
  elapsed_seconds: 300, remaining_seconds: 300, raw_score: 8, max_score: 10, band_score: null, server_time: now,
};
const data: Awaited<ReturnType<typeof getListeningReview>> = {
  review: { attempt, test_title: "Fictional test", answers: [] }, highlights: [],
  audio_asset: { id, original_name: "fictional.mp3", mime_type: "audio/mpeg", file_size: 100, content_url: `/assets/${id}/content` },
  parts: [{ id, title: "Fictional tour", order_index: 1, audio_start_seconds: 468, audio_end_seconds: 931,
    question_groups: [{ id, question_type: "short_answer", instruction: "Answer briefly.", config: {}, order_index: 0,
      questions: [{ id, number: 11, prompt: "Fictional question", config: { max_words: 2 }, answer_key: { kind: "TEXT", accepted: ["fixture"] }, explanation: null, order_index: 0 }] }] }],
};
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear();
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
  Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: vi.fn() });
});

it("shows the focused score, selected section and same clip without a Band", () => {
  const view = render(<ListeningReviewView data={data} />);
  expect(screen.getByText("Focused practice · Listening")).toBeInTheDocument();
  expect(screen.getByText("Section 2 · Fictional tour")).toBeInTheDocument();
  expect(screen.getByText("8 / 10")).toBeInTheDocument();
  expect(screen.getByText("80.0% accuracy")).toBeInTheDocument();
  expect(screen.queryByText(/Band|Official band unavailable/)).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Review sections")).not.toBeInTheDocument();
  expect(screen.getByText("Question 11")).toBeInTheDocument();
  expect(screen.queryByText("Question 1")).not.toBeInTheDocument();
  const audio = view.container.querySelector("audio")!;
  Object.defineProperty(audio, "duration", { configurable: true, value: 1000 });
  fireEvent.loadedMetadata(audio);
  expect(audio.currentTime).toBe(468);
  expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", "463");
});

it("keeps the full recording in full Listening review even with saved ranges", () => {
  const view = render(<ListeningReviewView data={{ ...data, review: { ...data.review, attempt: { ...attempt, scope: "FULL_MODULE", focused_unit: null } } }} />);
  const audio = view.container.querySelector("audio")!;
  Object.defineProperty(audio, "duration", { configurable: true, value: 1000 });
  fireEvent.loadedMetadata(audio);
  expect(audio.currentTime).toBe(0);
  expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", "1000");
  expect(screen.getByLabelText("Review sections")).toBeInTheDocument();
});

it("offers the full recording for a focused section without a range", () => {
  const view = render(<ListeningReviewView data={{ ...data, parts: data.parts.map((part) => ({ ...part, audio_start_seconds: null, audio_end_seconds: null })) }} />);
  expect(screen.getByText("Section audio range is not configured. Full recording is available.")).toHaveClass("notice");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  const audio = view.container.querySelector("audio")!;
  expect(audio).not.toBeNull();
  Object.defineProperty(audio, "duration", { configurable: true, value: 1000 });
  fireEvent.loadedMetadata(audio);
  expect(audio.currentTime).toBe(0);
  expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", "1000");
  expect(screen.getByLabelText("Audio seek")).not.toBeDisabled();
  expect(screen.getByLabelText("Playback speed")).not.toBeDisabled();
  expect(screen.getByText("80.0% accuracy")).toBeInTheDocument();
  expect(screen.queryByText(/Band|Official band unavailable/)).not.toBeInTheDocument();
  expect(screen.getByText("Question 11")).toBeInTheDocument();
});

it("reviews focused answers without audio and offers the external-recording notice", () => {
  const view = render(<ListeningReviewView data={{ ...data, audio_asset: null }} />);
  expect(view.container.querySelector("audio")).toBeNull();
  expect(screen.queryByLabelText("Listening audio player")).not.toBeInTheDocument();
  expect(screen.getByText("No recording is attached. You can continue with the questions and use an external recording if needed.")).toHaveClass("notice");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("8 / 10")).toBeInTheDocument();
  expect(screen.getByText("80.0% accuracy")).toBeInTheDocument();
  expect(screen.queryByText(/Band|Official band unavailable/)).not.toBeInTheDocument();
  expect(screen.getByText("Question 11")).toBeInTheDocument();
});

it.each(["COUNTDOWN", "COUNT_UP"] as const)("retains focused Listening paused %s context and resume", async (mode) => {
  vi.mocked(resumeAttempt).mockResolvedValue(attempt);
  const exam: ExamPayload = { attempt: { ...attempt, status: "PAUSED", timer_mode: mode }, test_title: "Fictional test", passages: [], writing_tasks: [], listening_parts: [], listening_audio_asset: data.audio_asset, highlights: [] };
  render(<PausedAttemptGate exam={exam} />);
  expect(screen.getByText("Listening · Section 2")).toBeInTheDocument();
  expect(screen.getByText("Focused practice · Paused")).toBeInTheDocument();
  expect(screen.getByText(mode === "COUNTDOWN" ? "Remaining: 05:00" : "Practice time: 05:00")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Resume attempt" }));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
  expect(resumeAttempt).toHaveBeenCalledWith(id);
});
