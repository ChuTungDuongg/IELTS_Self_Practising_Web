import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ReadingReviewView } from "@/features/reading/reading-review";
import type { ExamPayload } from "@/lib/api/exam";
import { deleteAllHighlights } from "@/lib/api/exam";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, recordActivity: vi.fn(), saveAnswer: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, createHighlight: vi.fn(), deleteAllHighlights: vi.fn().mockResolvedValue(undefined), deleteHighlight: vi.fn(), getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
});

const intro = "Do the following statements agree with the information given in Reading Passage 3?";
const questionId = "77777777-7777-4777-8777-777777777777";
const groupId = "66666666-6666-4666-8666-666666666666";
const passageId = "55555555-5555-4555-8555-555555555555";

const attempt = {
  attempt_id: "11111111-1111-4111-8111-111111111111",
  test_version_id: "22222222-2222-4222-8222-222222222222",
  module: "READING", status: "IN_PROGRESS", finished_reason: null,
  timer_mode: "COUNT_UP", timer_limit_seconds: null,
  started_at: new Date().toISOString(), paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: new Date().toISOString(), finished_at: null,
  elapsed_seconds: 0, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: new Date().toISOString(),
};

describe("Reading question group instructions", () => {
  it("renders one registry instruction in the candidate interface using actual passage order", () => {
    const initial = {
      attempt, test_title: "Practice", highlights: [], listening_audio_asset: null, listening_parts: [], writing_tasks: [],
      passages: [{ id: passageId, title: "Passage", order_index: 2, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, order_index: 0, value: null, flagged: false, answer_revision: 0 }] }] }],
    } as ExamPayload;

    render(<ReadingRunner initial={initial} />);

    expect(screen.getAllByText(intro)).toHaveLength(1);
  });

  it("changes the application theme without resetting candidate answers", () => {
    document.documentElement.dataset.theme = "light";
    const initial = {
      attempt, test_title: "Practice", highlights: [], listening_audio_asset: null, listening_parts: [], writing_tasks: [],
      passages: [{ id: passageId, title: "Passage", order_index: 2, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, order_index: 0, value: null, flagged: false, answer_revision: 0 }] }] }],
    } as ExamPayload;

    render(<ReadingRunner initial={initial} />);
    fireEvent.click(screen.getByRole("radio", { name: "TRUE" }));
    fireEvent.click(screen.getByRole("button", { name: "Toggle color theme" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("radio", { name: "TRUE" })).toBeChecked();
  });

  it("renders the same instruction once in review", () => {
    const data = {
      review: { attempt: { ...attempt, status: "SUBMITTED", raw_score: 35, max_score: 40, band_score: 8.0 }, test_title: "Practice", answers: [{ question_id: questionId, question_number: 1, prompt: "Statement", value: "TRUE", answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, is_correct: true, explanation: null }] },
      passages: [{ id: passageId, title: "Passage", order_index: 2, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, explanation: null, order_index: 0 }] }] }],
    };

    render(<ReadingReviewView data={data as never} />);

    expect(screen.getAllByText(intro)).toHaveLength(1);
    expect(screen.getByText("35 / 40")).toBeInTheDocument();
    expect(screen.getByText("Band 8.0")).toBeInTheDocument();
  });

  it("shares the compact multiline completion presentation between candidate and review", () => {
    const completionInstruction = "Complete the notes below.\nUse words from the passage.";
    const secondQuestionId = "77777777-7777-4777-8777-777777777778";
    const completionConfig = { mode: "SENTENCE", blocks: [
      { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "The fictional answer is " }, { id: crypto.randomUUID(), type: "GAP", question_id: questionId }, { id: crypto.randomUUID(), type: "TEXT", text: "." }] },
      { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "The second fictional answer is " }, { id: crypto.randomUUID(), type: "GAP", question_id: secondQuestionId }, { id: crypto.randomUUID(), type: "TEXT", text: "." }] },
    ] };
    const initial = {
      attempt, test_title: "Practice", highlights: [], listening_audio_asset: null, listening_parts: [], writing_tasks: [],
      passages: [{ id: passageId, title: "Passage", order_index: 0, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "text_completion", instruction: completionInstruction, config: completionConfig, order_index: 0, questions: [
        { id: questionId, number: 1, prompt: "", config: { max_words: 2, max_numbers: 0 }, order_index: 0, value: null, flagged: false, answer_revision: 0 },
        { id: secondQuestionId, number: 2, prompt: "", config: { max_words: 2, max_numbers: 0 }, order_index: 1, value: null, flagged: false, answer_revision: 0 },
      ] }] }],
    } as ExamPayload;
    const candidate = render(<ReadingRunner initial={initial} />);
    expect(candidate.container.querySelectorAll(".text-completion-line")).toHaveLength(2);
    expect(candidate.container.querySelectorAll(".completion-gap-inline")).toHaveLength(2);
    expect(candidate.container.querySelector(".question-group-instruction-text")?.textContent).toBe(completionInstruction);
    expect(screen.queryByText(/max 2 words/i)).not.toBeInTheDocument();
    candidate.unmount();

    const data = {
      review: { attempt: { ...attempt, status: "SUBMITTED", raw_score: 2, max_score: 2 }, test_title: "Practice", answers: [
        { question_id: questionId, question_number: 1, prompt: "", value: "fictional", answer_key: { kind: "TEXT", accepted: ["fictional"], case_sensitive: false }, is_correct: true, explanation: null },
        { question_id: secondQuestionId, question_number: 2, prompt: "", value: "invented", answer_key: { kind: "TEXT", accepted: ["invented"], case_sensitive: false }, is_correct: true, explanation: null },
      ] },
      passages: [{ id: passageId, title: "Passage", order_index: 0, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "text_completion", instruction: completionInstruction, config: completionConfig, order_index: 0, questions: [
        { id: questionId, number: 1, prompt: "", config: { max_words: 2, max_numbers: 0 }, answer_key: { kind: "TEXT", accepted: ["fictional"], case_sensitive: false }, explanation: null, order_index: 0 },
        { id: secondQuestionId, number: 2, prompt: "", config: { max_words: 2, max_numbers: 0 }, answer_key: { kind: "TEXT", accepted: ["invented"], case_sensitive: false }, explanation: null, order_index: 1 },
      ] }] }],
    };
    const review = render(<ReadingReviewView data={data as never} />);
    expect(review.container.querySelectorAll(".text-completion-line")).toHaveLength(2);
    expect(review.container.querySelectorAll(".completion-gap-inline")).toHaveLength(2);
    expect(review.container.querySelector(".question-group-instruction-text")?.textContent).toBe(completionInstruction);
    expect(screen.queryByText(/max 2 words/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /flag question/i })).not.toBeInTheDocument();
  });

  it("confirms and bulk deletes all highlight target types with one request", async () => {
    vi.mocked(deleteAllHighlights).mockClear();
    const initial = {
      attempt, test_title: "Practice", listening_audio_asset: null, listening_parts: [], writing_tasks: [],
      highlights: [{ id: "33333333-3333-4333-8333-333333333333", target_kind: "QUESTION_PROMPT", target_id: questionId, segment_id: null, passage_id: null, start_block_id: null, end_block_id: null, start_offset: 0, end_offset: 9, selected_text: "Statement", created_at: new Date().toISOString() }],
      passages: [{ id: passageId, title: "Passage", order_index: 0, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, order_index: 0, value: null, flagged: false, answer_revision: 0 }] }] }],
    } as ExamPayload;
    render(<ReadingRunner initial={initial} />);
    expect(screen.getByText("1 highlight")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete all" }));
    expect(screen.getByText("All highlights in this attempt will be removed. This action cannot be undone.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete all highlights" }));
    await waitFor(() => expect(deleteAllHighlights).toHaveBeenCalledTimes(1));
    expect(screen.getByText("0 highlights")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete all" })).not.toBeInTheDocument();
  });

  it("keeps highlights and the dialog visible when bulk deletion fails", async () => {
    vi.mocked(deleteAllHighlights).mockClear();
    vi.mocked(deleteAllHighlights).mockRejectedValueOnce(new Error("offline"));
    const initial = {
      attempt, test_title: "Practice", listening_audio_asset: null, listening_parts: [], writing_tasks: [],
      highlights: [{ id: "33333333-3333-4333-8333-333333333333", target_kind: "QUESTION_PROMPT", target_id: questionId, segment_id: null, passage_id: null, start_block_id: null, end_block_id: null, start_offset: 0, end_offset: 9, selected_text: "Statement", created_at: new Date().toISOString() }],
      passages: [{ id: passageId, title: "Passage", order_index: 0, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, order_index: 0, value: null, flagged: false, answer_revision: 0 }] }] }],
    } as ExamPayload;
    render(<ReadingRunner initial={initial} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete all" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete all highlights" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not delete the highlights");
    expect(deleteAllHighlights).toHaveBeenCalledTimes(1);
    expect(screen.getByText("1 highlight")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Delete all highlights?" })).toBeInTheDocument();
  });
});
