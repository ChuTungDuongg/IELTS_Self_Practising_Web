import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import { createHighlight, getExam, type ExamPayload, type Highlight } from "@/lib/api/exam";
import type { BuilderPassage, BuilderVersion } from "@/lib/api/builder";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/attempts", async original => ({
  ...await original<typeof import("@/lib/api/attempts")>(), recordActivity: vi.fn(), recordNavigation: vi.fn(),
}));
vi.mock("@/lib/api/exam", async original => ({
  ...await original<typeof import("@/lib/api/exam")>(), createHighlight: vi.fn(),
}));

const passageId = "11111111-1111-4111-8111-111111111111";
const blockId = "22222222-2222-4222-8222-222222222222";
const multiline = "A physician wrote about careful reasoning.\n\nA lawyer made the same point.\n\nI hope you will share this fictional example.";

function fixtures(text = multiline) {
  const passage: BuilderPassage = {
    id: passageId, revision: 1, title: "Fictional passage", order_index: 0,
    blocks: [
      { id: blockId, type: "paragraph", label: "G", text },
      { id: "33333333-3333-4333-8333-333333333333", type: "heading", label: null, text: "Fictional heading\ncontinued" },
    ],
    question_groups: [],
  };
  const now = new Date().toISOString();
  const exam: ExamPayload = {
    attempt: {
      attempt_id: "44444444-4444-4444-8444-444444444444", test_version_id: "55555555-5555-4555-8555-555555555555",
      module: "READING", status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null,
      scope: "FULL_MODULE", attempt_context: "STANDALONE", focused_unit: null,
      started_at: now, paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: now, finished_at: null,
      elapsed_seconds: 0, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: now,
    },
    test_title: "Fictional formatting practice", passages: [{ ...passage, question_groups: [] }], highlights: [],
    listening_audio_asset: null, listening_parts: [], writing_tasks: [],
  };
  const version: BuilderVersion = {
    id: exam.attempt.test_version_id, test_id: "66666666-6666-4666-8666-666666666666", test_title: exam.test_title, version_number: 1, status: "DRAFT",
    modules: [{ id: "77777777-7777-4777-8777-777777777777", revision: 1, module_type: "READING", title: null,
      recommended_duration_seconds: 3600, audio_asset: null, passages: [passage], listening_parts: [], writing_tasks: [] }],
  };
  return { passage, exam, version };
}

function savedHighlight(): Highlight {
  return {
    id: "88888888-8888-4888-8888-888888888888", target_kind: "PASSAGE_BLOCK", target_id: passageId, segment_id: blockId,
    passage_id: null, start_block_id: null, end_block_id: null,
    start_offset: 44, end_offset: 52, selected_text: "A lawyer", created_at: new Date().toISOString(),
  };
}

function reviewData(exam: ExamPayload, passage: BuilderPassage) {
  return { review: { attempt: { ...exam.attempt, status: "SUBMITTED" as const, raw_score: 0, max_score: 0 }, test_title: exam.test_title, answers: [] },
    passages: [passage], highlights: exam.highlights };
}

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); window.getSelection()?.removeAllRanges(); });

describe("authored Reading paragraph formatting", () => {
  it("keeps the original multiline TextBlock through exam response validation", async () => {
    const { exam, passage } = fixtures();
    const loaded = await getExam(exam.attempt.attempt_id, vi.fn().mockResolvedValue(JSON.parse(JSON.stringify(exam))));
    expect(loaded.passages[0].blocks).toEqual(passage.blocks);
    expect(loaded.passages[0].blocks.filter(block => block.type === "paragraph")).toEqual([{ id: blockId, type: "paragraph", label: "G", text: multiline }]);
  });

  const rows = (["exam", "review", "preview"] as const).flatMap(surface => [
    { surface, name: "blank lines", text: multiline },
    { surface, name: "single line break", text: "First.\nSecond." },
    { surface, name: "single-line text", text: "Unchanged single-line paragraph." },
  ]);
  it.each(rows)("$surface keeps $name in one labelled paragraph using the scoped whitespace contract", ({ surface, text }) => {
    const { exam, passage, version } = fixtures(text);
    const view = render(surface === "exam" ? <ReadingRunner initial={exam} /> : surface === "review"
      ? <ReadingReviewView data={reviewData(exam, passage)} /> : <DraftPreview version={version} moduleType="READING" />);
    const body = view.container.querySelector(surface === "review" ? ".review-passage-body" : ".exam-passage-body")!;
    expect(body.querySelectorAll("p")).toHaveLength(1);
    const paragraph = body.querySelector("p")!;
    expect(paragraph).toHaveClass("reading-passage-paragraph");
    expect(within(paragraph).getAllByText("G", { exact: true })).toHaveLength(1);
    expect(paragraph.querySelectorAll(".reading-passage-text")).toHaveLength(1);
    expect(paragraph.querySelector(".reading-passage-text")?.textContent).toBe(text);
    expect(paragraph.querySelectorAll("[data-highlight-target]")).toHaveLength(surface === "preview" ? 0 : 1);
    expect(body.querySelector("h3")?.textContent).toBe("Fictional heading\ncontinued");
    expect(body.querySelector("h3 .reading-passage-text")).toBeNull();
    expect(passage.blocks.filter(block => block.type === "paragraph")).toEqual([{ id: blockId, type: "paragraph", label: "G", text }]);
  });

  it("creates a later-subparagraph highlight with absolute offsets and restores it in exam and review", async () => {
    const { exam, passage } = fixtures();
    const stored = savedHighlight();
    vi.mocked(createHighlight).mockResolvedValue(stored);
    const candidate = render(<ReadingRunner initial={exam} />);
    const text = candidate.container.querySelector(".exam-passage-body [data-highlight-target]")!;
    expect(text.textContent).toBe(multiline);
    const range = document.createRange();
    range.setStart(text.firstChild!, 44);
    range.setEnd(text.firstChild!, 52);
    Object.defineProperty(range, "getBoundingClientRect", { value: () => ({ left: 10, top: 20, width: 40, height: 10 }) });
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(text);
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));
    await waitFor(() => expect(createHighlight).toHaveBeenCalledWith(exam.attempt.attempt_id, {
      target_kind: "PASSAGE_BLOCK", target_id: passageId, segment_id: blockId,
      start_offset: 44, end_offset: 52, selected_text: "A lawyer",
    }));
    await screen.findByRole("button", { name: "Highlight: A lawyer. Open options" });
    expect(text.textContent).toBe(multiline);
    expect(text.querySelectorAll("mark")).toHaveLength(1);
    candidate.unmount();
    const reviewed = render(<ReadingReviewView data={reviewData({ ...exam, highlights: [stored] }, passage)} />);
    const restored = reviewed.container.querySelector(".review-passage-body [data-highlight-target]")!;
    expect(restored.textContent).toBe(multiline);
    expect(restored.querySelector("mark")?.textContent).toBe("A lawyer");
    expect(screen.queryByRole("button", { name: /Highlight: A lawyer/ })).not.toBeInTheDocument();
    expect(reviewed.container.querySelectorAll(".review-passage-body [data-highlight-target]")).toHaveLength(2);
  });
});
