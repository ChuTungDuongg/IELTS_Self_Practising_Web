import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
import { normalizeCompletionSegments, normalizeTextCompletionOrder } from "@/features/questions/text-completion-canvas";
import type { QuestionGroupModel, TextCompletionBlock, TextCompletionLayout } from "@/features/questions/types";

function completionGroup(count = 3, mode: TextCompletionLayout["mode"] = "SENTENCE"): QuestionGroupModel {
  const group = questionRegistry.text_completion.createDefault(1);
  const questions = Array.from({ length: count }, (_, index) => {
    const question = questionRegistry.text_completion.createDefault(index + 1).questions[0];
    question.answer_key = { kind: "TEXT", accepted: [`answer-${index + 1}`, `alternative-${index + 1}`], case_sensitive: false };
    question.config = { max_words: index + 1, max_numbers: 1 };
    return { ...question, order_index: index };
  });
  const segments = questions.flatMap((question, index) => [
    { id: crypto.randomUUID(), type: "TEXT" as const, text: index ? ` text-${index + 1} ` : "Start " },
    { id: crypto.randomUUID(), type: "GAP" as const, question_id: question.id },
  ]);
  segments.push({ id: crypto.randomUUID(), type: "TEXT", text: " tail" });
  return { ...group, questions, config: { mode, blocks: [{ id: crypto.randomUUID(), segments }] } };
}

describe("text completion canvas", () => {
  it("normalizes adjacent TEXT while preserving spaces and punctuation", () => {
    const firstId = crypto.randomUUID();
    expect(normalizeCompletionSegments([
      { id: firstId, type: "TEXT", text: "hello " },
      { id: crypto.randomUUID(), type: "TEXT", text: "" },
      { id: crypto.randomUUID(), type: "TEXT", text: "world." },
    ])).toEqual([{ id: firstId, type: "TEXT", text: "hello world." }]);
  });

  it("renumbers by visual gap order without moving UUID-bound answer data", () => {
    const group = completionGroup(3);
    const layout = group.config as unknown as TextCompletionLayout;
    const gaps = layout.blocks[0].segments.filter((segment) => segment.type === "GAP");
    const text = layout.blocks[0].segments.filter((segment) => segment.type === "TEXT");
    const reordered = { ...layout, blocks: [{ ...layout.blocks[0], segments: [text[0], gaps[1], text[1], gaps[0], text[2], gaps[2], text[3]] }] };

    const normalized = normalizeTextCompletionOrder(group, reordered, 11);

    expect(normalized.questions.map((question) => question.number)).toEqual([11, 12, 13]);
    expect(normalized.questions.map((question) => question.id)).toEqual([group.questions[1].id, group.questions[0].id, group.questions[2].id]);
    expect(normalized.questions[0].answer_key.accepted).toEqual(["answer-2", "alternative-2"]);
    expect(normalized.questions[0].config.max_words).toBe(2);
  });

  it("adds Q14 at the real caret after a Q11-Q13 layout", () => {
    const group = completionGroup(3);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={14} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    const text = screen.getAllByRole("textbox", { name: /Paragraph 1 text segment/ }).at(-1)!;
    const range = document.createRange();
    range.setStart(text.firstChild!, 1);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(text);
    fireEvent.click(screen.getByRole("button", { name: "+ Insert gap" }));

    expect(screen.getByRole("button", { name: "Gap question 14" })).toHaveTextContent("Q14");
    expect(screen.getAllByRole("button", { name: /Gap question/ }).map((item) => item.textContent)).toEqual(["Q11", "Q12", "Q13", "Q14"]);
  });

  it("removes a middle gap through ConfirmDialog and closes the number range", async () => {
    const group = completionGroup(3);
    const retainedIds = [group.questions[0].id, group.questions[2].id];
    const confirm = vi.spyOn(window, "confirm");
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={14} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "Gap question 12" }));
    fireEvent.click(within(screen.getByRole("toolbar", { name: "Question 12 gap actions" })).getByRole("button", { name: "Remove gap" }));
    const dialog = screen.getByRole("dialog", { name: "Remove this gap?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove gap" }));

    expect(screen.getAllByRole("button", { name: /Gap question/ }).map((item) => item.textContent)).toEqual(["Q11", "Q12"]);
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    expect(saved.questions.map((question: { id?: string }) => question.id)).toEqual(retainedIds);
    expect(saved.questions[1].answer_key.accepted).toEqual(["answer-3", "alternative-3"]);
    expect(confirm).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("drags a gap to a character caret in the same paragraph without changing its question", async () => {
    const group = completionGroup(1);
    const layout = group.config as unknown as TextCompletionLayout;
    layout.blocks[0].segments = [
      { id: crypto.randomUUID(), type: "TEXT", text: "The main " },
      layout.blocks[0].segments.find((segment) => segment.type === "GAP")!,
      { id: crypto.randomUUID(), type: "TEXT", text: "source of income" },
    ];
    const questionId = group.questions[0].id;
    const answerKey = group.questions[0].answer_key;
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={12} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    const target = screen.getByRole("textbox", { name: "Paragraph 1 text segment 3" });
    const range = document.createRange();
    range.setStart(target.firstChild!, 7);
    range.collapse(true);
    Object.defineProperty(document, "caretRangeFromPoint", { configurable: true, value: vi.fn(() => range) });
    const dataTransfer = { effectAllowed: "none", setData: vi.fn() };
    const gap = screen.getByRole("button", { name: "Gap question 11" });
    const block = view.container.querySelector("[data-completion-block]")!;

    fireEvent.dragStart(gap, { dataTransfer });
    fireEvent.dragOver(block, { clientX: 50, clientY: 20, dataTransfer });
    expect(screen.getByLabelText("Gap drop position")).toBeInTheDocument();
    fireEvent.drop(block, { clientX: 50, clientY: 20, dataTransfer });
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    const savedLayout = saved.config as TextCompletionLayout;

    expect(saved.questions[0].id).toBe(questionId);
    expect(saved.questions[0].answer_key).toEqual(answerKey);
    expect(savedLayout.blocks[0].segments.map((segment: { type: string; text?: string }) => segment.type)).toEqual(["TEXT", "GAP", "TEXT"]);
    expect(savedLayout.blocks[0].segments[0].text).toBe("The main source ");
    expect(savedLayout.blocks[0].segments[2].text).toBe("of income");
    Reflect.deleteProperty(document, "caretRangeFromPoint");
  });

  it("reorders passage paragraphs and their gaps while retaining stable questions", async () => {
    const group = completionGroup(2, "PASSAGE");
    const layout = group.config as unknown as TextCompletionLayout;
    const firstGap = layout.blocks[0].segments.find((segment) => segment.type === "GAP")!;
    const secondGap = layout.blocks[0].segments.filter((segment) => segment.type === "GAP")[1];
    const blocks: TextCompletionBlock[] = [
      { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "First " }, firstGap] },
      { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "Second " }, secondGap] },
    ];
    group.config = { ...layout, blocks };
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "Move paragraph 2 up" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    expect(saved.questions.map((question: { id?: string }) => question.id)).toEqual([group.questions[1].id, group.questions[0].id]);
    expect(saved.questions.map((question: { number: number }) => question.number)).toEqual([11, 12]);
    expect(saved.questions[0].answer_key.accepted[0]).toBe("answer-2");
  });

  it("removes a passage paragraph through the shared dialog without native confirmation", async () => {
    const group = completionGroup(2, "PASSAGE");
    const layout = group.config as unknown as TextCompletionLayout;
    const [firstGap, secondGap] = layout.blocks[0].segments.filter((segment) => segment.type === "GAP");
    group.config = {
      ...layout,
      blocks: [
        { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "First " }, firstGap] },
        { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "Second " }, secondGap] },
      ],
    };
    const confirm = vi.spyOn(window, "confirm");
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Remove paragraph" })[0]);
    const dialog = screen.getByRole("dialog", { name: "Remove this paragraph?" });
    expect(within(dialog).getByText(/Every gap and linked question/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove paragraph" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const saved = onSave.mock.calls[0][0];
    expect(saved.questions).toHaveLength(1);
    expect(saved.questions[0].id).toBe(group.questions[1].id);
    expect(saved.questions[0].number).toBe(11);
    expect(saved.questions[0].answer_key.accepted).toEqual(["answer-2", "alternative-2"]);
    expect(confirm).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
});
