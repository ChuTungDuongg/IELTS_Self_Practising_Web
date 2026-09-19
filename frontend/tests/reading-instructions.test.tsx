import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ReadingReviewView } from "@/features/reading/reading-review";
import type { ExamPayload } from "@/lib/api/exam";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/attempts", () => ({ recordActivity: vi.fn(), saveAnswer: vi.fn() }));
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, createHighlight: vi.fn(), deleteHighlight: vi.fn(), getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
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
  started_at: new Date().toISOString(), deadline_at: null, last_active_at: new Date().toISOString(), finished_at: null,
  elapsed_seconds: 0, remaining_seconds: null, raw_score: null, max_score: null, server_time: new Date().toISOString(),
};

describe("Reading question group instructions", () => {
  it("renders one registry instruction in the candidate interface using actual passage order", () => {
    const initial = {
      attempt, test_title: "Practice", highlights: [], listening_audio_asset: null, listening_parts: [],
      passages: [{ id: passageId, title: "Passage", order_index: 2, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, order_index: 0, value: null, flagged: false }] }] }],
    } as ExamPayload;

    render(<ReadingRunner initial={initial} />);

    expect(screen.getAllByText(intro)).toHaveLength(1);
  });

  it("renders the same instruction once in review", () => {
    const data = {
      review: { attempt: { ...attempt, status: "SUBMITTED", raw_score: 1, max_score: 1 }, test_title: "Practice", answers: [{ question_id: questionId, question_number: 1, prompt: "Statement", value: "TRUE", answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, is_correct: true, explanation: null }] },
      passages: [{ id: passageId, title: "Passage", order_index: 2, blocks: [{ id: "44444444-4444-4444-8444-444444444444", type: "paragraph", label: "A", text: "Fictional text." }], question_groups: [{ id: groupId, question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, explanation: null, order_index: 0 }] }] }],
    };

    render(<ReadingReviewView data={data as never} />);

    expect(screen.getAllByText(intro)).toHaveLength(1);
  });
});
