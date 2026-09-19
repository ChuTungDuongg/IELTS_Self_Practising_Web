import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { textCompletionIntegrityErrors } from "@/features/questions/text-completion-integrity";
import { questionRegistry } from "@/features/questions/registry";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
import { normalizeCompletionSegments, normalizeTextCompletionOrder, TextCompletionCanvas } from "@/features/questions/text-completion-canvas";
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

function sentenceGroup(): QuestionGroupModel {
  const group = completionGroup(2);
  const layout = group.config as unknown as TextCompletionLayout;
  const [firstGap, secondGap] = layout.blocks[0].segments.filter((segment) => segment.type === "GAP");
  group.config = {
    mode: "SENTENCE",
    blocks: [
      { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "First sentence " }, firstGap] },
      { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "Second sentence " }, secondGap] },
    ],
  };
  return group;
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
    const text = screen.getAllByRole("textbox", { name: /Sentence 1 text segment/ }).at(-1)!;
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
    const gapId = layout.blocks[0].segments.find((segment) => segment.type === "GAP")!.id;
    const answerKey = group.questions[0].answer_key;
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={12} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    const target = screen.getByRole("textbox", { name: "Sentence 1 text segment 3" });
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
    expect(savedLayout.blocks[0].segments.find((segment) => segment.type === "GAP")?.id).toBe(gapId);
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

  it("adds a separate sentence block with a stable UUID and edits only that block", async () => {
    const group = completionGroup(1);
    const originalBlockId = (group.config as unknown as TextCompletionLayout).blocks[0].id;
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={12} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "+ Add sentence" }));
    expect(screen.getByText("Sentence 2")).toBeInTheDocument();
    const blocks = [...view.container.querySelectorAll<HTMLElement>("[data-completion-block]")];
    expect(blocks).toHaveLength(2);
    expect(blocks[0].dataset.completionBlock).toBe(originalBlockId);
    expect(blocks[1].dataset.completionBlock).toMatch(/^[0-9a-f-]{36}$/);
    expect(blocks[1].dataset.completionBlock).not.toBe(originalBlockId);

    const secondText = screen.getByRole("textbox", { name: "Sentence 2 text segment 1" });
    secondText.textContent = "A newly authored sentence";
    fireEvent.input(secondText);
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const savedLayout = onSave.mock.calls[0][0].config as TextCompletionLayout;
    expect(savedLayout.blocks[0].segments[0].text).toBe("Start ");
    expect(savedLayout.blocks[1].segments[0].text).toBe("A newly authored sentence");
  });

  it("inserts a new gap into the active sentence only", async () => {
    const group = completionGroup(1);
    const originalQuestionId = group.questions[0].id;
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={12} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "+ Add sentence" }));
    const secondText = screen.getByRole("textbox", { name: "Sentence 2 text segment 1" });
    secondText.textContent = "Second sentence";
    const range = document.createRange();
    range.setStart(secondText.firstChild!, 15);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(secondText);

    fireEvent.click(screen.getByRole("button", { name: "+ Insert gap" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    const savedLayout = saved.config as TextCompletionLayout;
    expect(savedLayout.blocks[0].segments.filter((segment) => segment.type === "GAP")).toHaveLength(1);
    expect(savedLayout.blocks[1].segments.filter((segment) => segment.type === "GAP")).toHaveLength(1);
    expect(saved.questions[0].id).toBe(originalQuestionId);
    expect(saved.questions[1].id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("splits a sentence block at the caret on Enter without persisting a newline", async () => {
    const group = completionGroup(1);
    const originalQuestionId = group.questions[0].id;
    const layout = group.config as unknown as TextCompletionLayout;
    const gap = layout.blocks[0].segments.find((segment) => segment.type === "GAP")!;
    layout.blocks[0].segments = [{ id: crypto.randomUUID(), type: "TEXT", text: "The travel industry is important" }, gap];
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={12} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    const text = screen.getByRole("textbox", { name: "Sentence 1 text segment 1" });
    const range = document.createRange();
    range.setStart(text.firstChild!, 23);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);

    fireEvent.keyDown(text, { key: "Enter" });
    expect(screen.getByText("Sentence 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const savedLayout = onSave.mock.calls[0][0].config as TextCompletionLayout;
    expect(savedLayout.blocks).toHaveLength(2);
    expect(savedLayout.blocks[0].segments[0].text).toBe("The travel industry is ");
    expect(savedLayout.blocks[1].segments[0].text).toBe("important");
    expect(savedLayout.blocks.flatMap((block) => block.segments).some((segment) => segment.text?.includes("\n"))).toBe(false);
    expect(savedLayout.blocks[1].segments.find((segment) => segment.type === "GAP")?.id).toBe(gap.id);
    expect(savedLayout.blocks[1].segments.find((segment) => segment.type === "GAP")?.question_id).toBe(originalQuestionId);
    expect(onSave.mock.calls[0][0].questions[0].id).toBe(originalQuestionId);
  });

  it("preserves sentence blocks and IDs when switching modes", async () => {
    const group = sentenceGroup();
    const originalLayout = structuredClone(group.config) as TextCompletionLayout;
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "PASSAGE" } });
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "SENTENCE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    expect(onSave.mock.calls[0][0].config).toEqual(originalLayout);
  });

  it("removes raw newlines from SENTENCE input but keeps PASSAGE input multiline", async () => {
    const sentence = completionGroup(1);
    const sentenceSave = vi.fn().mockResolvedValue(undefined);
    const sentenceView = render(<QuestionGroupEditor initial={sentence} nextQuestionNumber={11} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={sentenceSave} />);
    const sentenceText = screen.getByRole("textbox", { name: "Sentence 1 text segment 1" });
    sentenceText.textContent = "First line\nSecond line";
    fireEvent.input(sentenceText);
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(sentenceSave).toHaveBeenCalledTimes(1));
    expect((sentenceSave.mock.calls[0][0].config as TextCompletionLayout).blocks[0].segments[0].text).toBe("First line Second line");
    sentenceView.unmount();

    const passage = completionGroup(1, "PASSAGE");
    const passageSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={passage} nextQuestionNumber={11} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={passageSave} />);
    const passageText = screen.getByRole("textbox", { name: "Paragraph 1 text segment 1" });
    passageText.textContent = "First paragraph line\nSecond paragraph line";
    fireEvent.input(passageText);
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(passageSave).toHaveBeenCalledTimes(1));
    expect((passageSave.mock.calls[0][0].config as TextCompletionLayout).blocks[0].segments[0].text).toBe("First paragraph line\nSecond paragraph line");
  });

  it("reorders sentence blocks and renumbers questions by visual gap order", async () => {
    const group = sentenceGroup();
    const originalLayout = group.config as unknown as TextCompletionLayout;
    const originalBlockIds = originalLayout.blocks.map((block) => block.id);
    const originalGapIds = originalLayout.blocks.map((block) => block.segments.find((segment) => segment.type === "GAP")!.id);
    const originalQuestionIds = group.questions.map((question) => question.id);
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "Move sentence 2 up" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    expect((saved.config as TextCompletionLayout).blocks.map((block: TextCompletionBlock) => block.id)).toEqual([originalBlockIds[1], originalBlockIds[0]]);
    expect((saved.config as TextCompletionLayout).blocks.map((block) => block.segments.find((segment) => segment.type === "GAP")!.id)).toEqual([originalGapIds[1], originalGapIds[0]]);
    expect(saved.questions.map((question: { id?: string }) => question.id)).toEqual([originalQuestionIds[1], originalQuestionIds[0]]);
    expect(saved.questions.map((question: { number: number }) => question.number)).toEqual([11, 12]);
    expect(saved.questions[0].answer_key.accepted).toEqual(["answer-2", "alternative-2"]);
    expect(saved.questions[0].config).toEqual({ max_words: 2, max_numbers: 1 });
  });

  it("renders separate sentence rows in Builder Preview", () => {
    const group = sentenceGroup();
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    const lines = [...view.container.querySelectorAll(".group-preview .text-completion-line")];
    expect(lines).toHaveLength(2);
    expect(lines.map((line) => line.textContent)).toEqual(["First sentence 11", "Second sentence 12"]);
  });

  it("removes a sentence and its linked question through ConfirmDialog", async () => {
    const group = sentenceGroup();
    const retainedQuestionId = group.questions[1].id;
    const confirm = vi.spyOn(window, "confirm");
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Remove sentence" })[0]);
    const dialog = screen.getByRole("dialog", { name: "Remove this sentence?" });
    expect(within(dialog).getByText("Removing this sentence will also remove its linked questions and answer configuration.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove sentence" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    expect((saved.config as TextCompletionLayout).blocks).toHaveLength(1);
    expect(saved.questions).toHaveLength(1);
    expect(saved.questions[0].id).toBe(retainedQuestionId);
    expect(saved.questions[0].number).toBe(11);
    expect(confirm).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("normalizes a simple legacy newline sentence into separate blocks", async () => {
    const group = completionGroup(0);
    group.questions = [];
    group.config = { mode: "SENTENCE", blocks: [{ id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "First sentence\nSecond sentence\nThird sentence" }] }] };
    const onChange = vi.fn();
    render(<TextCompletionCanvas group={group} onChange={onChange} />);

    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    const normalized = onChange.mock.calls[0][0].config as TextCompletionLayout;
    expect(normalized.blocks.map((block) => block.segments[0].text)).toEqual(["First sentence", "Second sentence", "Third sentence"]);
    expect(new Set(normalized.blocks.map((block) => block.id)).size).toBe(3);
  });

  it("preserves ambiguous legacy newline data and surfaces a warning", () => {
    const group = completionGroup(1);
    const layout = group.config as unknown as TextCompletionLayout;
    const gap = layout.blocks[0].segments.find((segment) => segment.type === "GAP")!;
    layout.blocks[0].segments = [{ id: crypto.randomUUID(), type: "TEXT", text: "First line\nSecond line" }, gap];
    const onChange = vi.fn();
    render(<TextCompletionCanvas group={group} onChange={onChange} />);

    expect(screen.getByRole("alert")).toHaveTextContent("legacy line breaks");
    expect(onChange).not.toHaveBeenCalled();
    expect((group.config as unknown as TextCompletionLayout).blocks[0].segments[0].text).toBe("First line\nSecond line");
  });
});


describe("completion focus and integrity regressions", () => {
  it("keeps the same text node, segment ID, and middle caret across successive input", async () => {
    const group = completionGroup(1);
    const layout = group.config as unknown as TextCompletionLayout;
    layout.blocks[0].segments[0].text = "The travel industry is mjor";
    const id = layout.blocks[0].segments[0].id;
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    const editor = screen.getByRole("textbox", { name: "Sentence 1 text segment 1" });
    editor.focus();
    const node = editor.firstChild as Text;
    const offset = node.data.indexOf("mjor") + 1;
    const range = document.createRange();
    range.setStart(node, offset);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    // Model native typing without replacing the text node (jsdom has no editing engine).
    node.insertData(offset, "a");
    range.setStart(node, offset + 1);
    range.collapse(true);
    fireEvent.input(editor);
    expect(editor.textContent).toBe("The travel industry is major");
    expect(editor.firstChild).toBe(node);
    expect(window.getSelection()!.anchorOffset).toBe(offset + 1);
    expect(document.activeElement).toBe(editor);
    node.insertData(offset + 1, "!");
    range.setStart(node, offset + 2);
    range.collapse(true);
    fireEvent.input(editor);
    expect(editor.firstChild).toBe(node);
    expect(window.getSelection()!.anchorOffset).toBe(offset + 2);
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(onSave.mock.calls[0][0].config.blocks[0].segments[0].id).toBe(id);
  });

  it("focuses empty surface and trailing whitespace in one click without selecting a gap", () => {
    const group = completionGroup(1);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Gap question 1" }));
    expect(screen.getByRole("toolbar")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Sentence 1 completion editor"));
    const tail = screen.getByRole("textbox", { name: "Sentence 1 text segment 3" });
    expect(document.activeElement).toBe(tail);
    expect(window.getSelection()!.getRangeAt(0).comparePoint(tail, tail.childNodes.length)).toBe(0);
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Add sentence" }));
    fireEvent.click(screen.getByLabelText("Sentence 2 completion editor"));
    const empty = screen.getByRole("textbox", { name: "Sentence 2 text segment 1" });
    expect(document.activeElement).toBe(empty);
    empty.textContent = "New sentence";
    fireEvent.input(empty);
    expect(document.activeElement).toBe(empty);
    expect(screen.getByRole("textbox", { name: "Sentence 2 text segment 1" })).toBe(empty);
  });

  it("creates an editable trailing segment once when the sentence ends in a gap", () => {
    render(<QuestionGroupEditor initial={sentenceGroup()} nextQuestionNumber={3} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Sentence 1 completion editor"));
    const tail = screen.getByRole("textbox", { name: "Sentence 1 text segment 3" });
    expect(document.activeElement).toBe(tail);
    fireEvent.click(screen.getByLabelText("Sentence 1 completion editor"));
    expect(screen.getByRole("textbox", { name: "Sentence 1 text segment 3" })).toBe(tail);
  });

  it.each(["orphan gap", "orphan question", "duplicate gap", "duplicate block", "duplicate segment"])("preserves and blocks invalid data: %s", (problem) => {
    const group = completionGroup(2);
    const layout = group.config as unknown as TextCompletionLayout;
    const segments = layout.blocks[0].segments;
    if (problem === "orphan gap") segments[1].question_id = crypto.randomUUID();
    if (problem === "orphan question") segments.splice(1, 1);
    if (problem === "duplicate gap") segments[3].question_id = segments[1].question_id;
    if (problem === "duplicate block") layout.blocks.push(structuredClone(layout.blocks[0]));
    if (problem === "duplicate segment") segments[2].id = segments[0].id;
    expect(textCompletionIntegrityErrors(group).length).toBeGreaterThan(0);
    const normalized = normalizeTextCompletionOrder(group, layout, 11);
    expect(normalized.questions).toEqual(group.questions);
    expect(normalized.config).toEqual(layout);
    // Duplicate React keys are diagnosed by the integrity helper before use in this test.
    if (problem.startsWith("duplicate") && problem !== "duplicate gap") return;
    const onSave = vi.fn();
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={3} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save group" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("lets the author explicitly repair an orphan gap and retains its answer after reopen", async () => {
    const group = completionGroup(1);
    (group.config as unknown as TextCompletionLayout).blocks[0].segments[1].question_id = crypto.randomUUID();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Gap question unknown" }));
    fireEvent.change(screen.getByLabelText("Link selected gap to question"), { target: { value: group.questions[0].id } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    const saved = JSON.parse(JSON.stringify(onSave.mock.calls[0][0]));
    expect(saved.questions[0]).toEqual(group.questions[0]);
    view.unmount();
    render(<QuestionGroupEditor initial={saved} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
    const scroll = vi.fn();
    document.getElementById(`text-answer-${group.questions[0].id}`)!.scrollIntoView = scroll;
    fireEvent.click(screen.getByRole("button", { name: "Gap question 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit answer" }));
    expect(scroll).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Correct answer")).toHaveValue("answer-1");
    expect(screen.getByLabelText("Alternative answer 1")).toHaveValue("alternative-1");
  });
});


it("explicitly adds an orphan question's missing gap without replacing its answer", async () => {
  const group = completionGroup(1);
  (group.config as unknown as TextCompletionLayout).blocks[0].segments.splice(1, 1);
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(<QuestionGroupEditor initial={group} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
  fireEvent.click(screen.getByRole("button", { name: "Add missing gap for Q1 to sentence 1" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save group" }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[0][0].questions).toEqual(group.questions);
  expect(textCompletionIntegrityErrors(onSave.mock.calls[0][0])).toEqual([]);
});


it("explicitly creates an answer for a broken gap whose original question was lost", async () => {
  const group = completionGroup(1);
  const originalLayout = structuredClone(group.config) as TextCompletionLayout;
  group.questions = [];
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(<QuestionGroupEditor initial={group} nextQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);
  expect(screen.getByRole("button", { name: "Save group" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Gap question unknown" }));
  fireEvent.click(screen.getByRole("button", { name: "Create answer for this gap" }));
  expect(screen.getByRole("button", { name: "Gap question 11" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Correct answer"), { target: { value: "recovered answer" } });
  fireEvent.click(screen.getByRole("button", { name: "Save group" }));
  await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  const saved = onSave.mock.calls[0][0];
  expect(textCompletionIntegrityErrors(saved)).toEqual([]);
  expect(saved.config.blocks[0].segments.map((segment: {id: string}) => segment.id)).toEqual(originalLayout.blocks[0].segments.map(segment => segment.id));
  expect(saved.config.blocks[0].segments[0].text).toBe("Start ");
  expect(saved.questions[0].answer_key.accepted).toEqual(["recovered answer"]);
  expect(saved.questions[0].id).toBe(saved.config.blocks[0].segments[1].question_id);
});
