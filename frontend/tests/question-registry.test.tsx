import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { MatchingHeadingsEditor, MultipleChoiceEditor, TextCompletionEditor } from "@/features/questions/editors";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
import { QuestionGroupInstruction, resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import type { ExamGroup } from "@/features/questions/types";

describe("question registry", () => {
  it("creates a structured MCQ with an inline answer key", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    const options = group.questions[0].config.options as Array<{ id: string }>;
    expect(group.questions[0].number).toBe(7);
    expect(options).toHaveLength(2);
    expect(group.questions[0].answer_key.value).toBe(options[0].id);
    expect(options[0].id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("routes exam answers through the registered renderer", () => {
    const group = questionRegistry.true_false_not_given.createDefault(3) as ExamGroup;
    group.id = crypto.randomUUID();
    group.questions[0].id = crypto.randomUUID();
    const onAnswer = vi.fn();
    const Renderer = questionRegistry.true_false_not_given.ExamRenderer;
    render(<Renderer group={group} values={{}} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByLabelText("FALSE"));
    expect(onAnswer).toHaveBeenCalledWith(group.questions[0].id, "FALSE");
  });

  it("registers YES / NO / NOT GIVEN as a distinct canonical type", () => {
    const group = questionRegistry.yes_no_not_given.createDefault(4) as ExamGroup;
    group.id = crypto.randomUUID();
    group.questions[0].id = crypto.randomUUID();
    const onAnswer = vi.fn();
    const Renderer = questionRegistry.yes_no_not_given.ExamRenderer;
    render(<Renderer group={group} values={{}} onAnswer={onAnswer} />);

    fireEvent.click(screen.getByLabelText("NOT GIVEN"));

    expect(group.question_type).toBe("yes_no_not_given");
    expect(onAnswer).toHaveBeenCalledWith(group.questions[0].id, "NOT_GIVEN");
  });

  it("stores the visible NOT GIVEN editor choice as NOT_GIVEN", () => {
    const group = questionRegistry.yes_no_not_given.createDefault(4);
    const onChange = vi.fn();
    const Editor = questionRegistry.yes_no_not_given.BuilderEditor;
    render(<Editor group={group} onChange={onChange} />);

    fireEvent.click(screen.getByLabelText("NOT GIVEN"));

    expect(onChange.mock.calls.at(-1)?.[0].questions[0].answer_key.value).toBe("NOT_GIVEN");
  });

  it("uses different IELTS semantics for TFNG and YNNG", () => {
    const tfng = questionRegistry.true_false_not_given.createDefault(1);
    const ynng = questionRegistry.yes_no_not_given.createDefault(2);
    tfng.instruction = "";
    ynng.instruction = "";

    const tfngInstruction = resolveQuestionGroupInstruction(tfng, { passageNumber: 3 });
    const ynngInstruction = resolveQuestionGroupInstruction(ynng, { passageNumber: 3 });

    expect(tfngInstruction.intro).toContain("information given in Reading Passage 3");
    expect(ynngInstruction.intro).toContain("views/claims of the writer in Reading Passage 3");
    expect(tfngInstruction.options?.map((option) => option.label)).toEqual(["TRUE", "FALSE", "NOT GIVEN"]);
    expect(ynngInstruction.options?.map((option) => option.label)).toEqual(["YES", "NO", "NOT GIVEN"]);
  });

  it("lets a custom instruction override the registry fallback", () => {
    const group = questionRegistry.true_false_not_given.createDefault(1);
    group.instruction = "Use the tutor's custom direction.";
    render(<QuestionGroupInstruction group={group} passageNumber={2} />);

    expect(screen.getByText("Use the tutor's custom direction.")).toBeInTheDocument();
    expect(screen.queryByText(/information given in Reading Passage 2/)).not.toBeInTheDocument();
  });

  it("generates word and number limits from the actual config", () => {
    const group = questionRegistry.text_completion.createDefault(8);
    group.instruction = "";
    group.questions[0].config = { max_words: 3, max_numbers: 1 };

    const instruction = resolveQuestionGroupInstruction(group, { passageNumber: 1 });

    expect(instruction.intro).toContain("NO MORE THAN 3 WORDS");
    expect(instruction.intro).toContain("1 NUMBER");
  });

  it("inserts a stable text-completion gap at the active caret", () => {
    const group = questionRegistry.text_completion.createDefault(11);
    const block = (group.config.blocks as Array<{ segments: Array<{ id: string; type: string; text?: string }> }>)[0];
    block.segments = [{ id: crypto.randomUUID(), type: "TEXT", text: "source of income" }];
    group.questions = [];
    const onChange = vi.fn();
    render(<TextCompletionEditor group={group} onChange={onChange} />);
    const text = screen.getByLabelText("Paragraph 1 text segment") as HTMLTextAreaElement;
    text.focus();
    text.setSelectionRange(6, 6);
    fireEvent.select(text);
    fireEvent.click(screen.getByRole("button", { name: "+ Insert gap" }));
    const updated = onChange.mock.calls.at(-1)?.[0];
    expect(updated.config.blocks[0].segments.map((segment: { type: string; text?: string }) => segment.type)).toEqual(["TEXT", "GAP", "TEXT"]);
    expect(updated.config.blocks[0].segments[0].text).toBe("source");
    expect(updated.config.blocks[0].segments[2].text).toBe(" of income");
    expect(updated.config.blocks[0].segments[1].question_id).toBe(updated.questions[0].id);
  });

  it("renders multiple text-completion gaps inline in one paragraph", () => {
    const group = questionRegistry.text_completion.createDefault(11) as ExamGroup;
    group.id = crypto.randomUUID();
    const second = { ...group.questions[0], id: crypto.randomUUID(), number: 12, order_index: 1 };
    group.questions.push(second);
    const block = (group.config.blocks as Array<{ segments: Array<Record<string, unknown>> }>)[0];
    block.segments.push(
      { id: crypto.randomUUID(), type: "TEXT", text: " and " },
      { id: crypto.randomUUID(), type: "GAP", question_id: second.id },
      { id: crypto.randomUUID(), type: "TEXT", text: "." },
    );
    const Renderer = questionRegistry.text_completion.ExamRenderer;
    render(<Renderer group={group} values={{}} onAnswer={vi.fn()} />);
    expect(screen.getByLabelText("Question 11")).toBeInTheDocument();
    expect(screen.getByLabelText("Question 12")).toBeInTheDocument();
    expect(screen.getAllByRole("textbox")).toHaveLength(2);
  });

  it("keeps punctuation inside one primary or alternative answer", () => {
    const group = questionRegistry.text_completion.createDefault(1);
    group.questions[0].answer_key = { kind: "TEXT", accepted: ["Athens, Greece", "the capital, Athens"], case_sensitive: false };
    const onChange = vi.fn();
    render(<TextCompletionEditor group={group} onChange={onChange} />);
    expect(screen.getByDisplayValue("Athens, Greece")).toBeInTheDocument();
    expect(screen.getByDisplayValue("the capital, Athens")).toBeInTheDocument();
  });

  it("keeps heading identity stable while labels and order change", () => {
    const group = questionRegistry.matching_headings.createDefault(1);
    const firstId = (group.config.options as Array<{ id: string }>)[0].id;
    const onChange = vi.fn();
    render(<MatchingHeadingsEditor group={group} onChange={onChange} passageBlocks={[]} />);
    fireEvent.change(screen.getByLabelText("Heading 1 label"), { target: { value: "ii" } });
    const relabelled = onChange.mock.calls.at(-1)?.[0];
    expect(relabelled.config.options[0].id).toBe(firstId);
    fireEvent.click(screen.getByLabelText("Move heading i down"));
    const reordered = onChange.mock.calls.at(-1)?.[0];
    expect(reordered.config.options[1].id).toBe(firstId);
  });

  it("uses stable keys even while visible heading labels are duplicated", () => {
    const group = questionRegistry.matching_headings.createDefault(1);
    const options = group.config.options as Array<{ id: string; label: string; text: string }>;
    group.config.options = options.map((option) => ({ ...option, label: "i" }));
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<MatchingHeadingsEditor group={group} onChange={vi.fn()} passageBlocks={[]} />);
    expect(screen.getByText(/Duplicate heading labels/)).toBeInTheDocument();
    expect(error.mock.calls.flat().join(" ")).not.toContain("same key");
    error.mockRestore();
  });

  it("stores actual passage block and heading UUIDs in assignments", () => {
    const group = questionRegistry.matching_headings.createDefault(1);
    const block = { id: crypto.randomUUID(), type: "paragraph" as const, label: "A", text: "Tourism is economically significant." };
    const onChange = vi.fn();
    const view = render(<MatchingHeadingsEditor group={group} onChange={onChange} passageBlocks={[block]} />);
    fireEvent.change(within(view.container).getByLabelText("Question 1 paragraph"), { target: { value: block.id } });
    expect(onChange.mock.calls.at(-1)?.[0].questions[0].config.target_block_id).toBe(block.id);
    const headingId = (group.config.options as Array<{ id: string }>)[1].id;
    fireEvent.change(within(view.container).getByLabelText("Question 1 correct heading"), { target: { value: headingId } });
    expect(onChange.mock.calls.at(-1)?.[0].questions[0].answer_key.value).toBe(headingId);
  });

  it("blocks deleting a heading while an assignment references it", () => {
    const group = questionRegistry.matching_headings.createDefault(1);
    const view = render(<MatchingHeadingsEditor group={group} onChange={vi.fn()} passageBlocks={[]} />);
    const removeButtons = within(view.container).getAllByRole("button", { name: "Remove" });
    expect(removeButtons[0]).toBeDisabled();
    expect(within(view.container).getByText("Used by Q1")).toBeInTheDocument();
    expect(removeButtons[1]).not.toBeDisabled();
  });

  it("continues numbering for multiple unsaved questions without regenerating IDs", () => {
    const group = questionRegistry.multiple_choice.createDefault(1);
    const originalId = group.questions[0].id;
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    expect(screen.getByText("Question 2")).toBeInTheDocument();
    expect(screen.getByText("Question 3")).toBeInTheDocument();
    expect(group.questions[0].id).toBe(originalId);
  });

  it("reorders questions without regenerating IDs and keeps display numbers canonical", () => {
    const group = questionRegistry.multiple_choice.createDefault(1);
    const second = questionRegistry.multiple_choice.createDefault(2).questions[0];
    group.questions.push({ ...second, order_index: 1 });
    const firstId = group.questions[0].id;
    const secondId = group.questions[1].id;
    const onChange = vi.fn();
    const view = render(<MultipleChoiceEditor group={group} onChange={onChange} />);
    fireEvent.click(within(view.container).getAllByRole("button", { name: "Move question down" })[0]);
    const reordered = onChange.mock.calls.at(-1)?.[0];
    expect(reordered.questions.map((question: { id?: string }) => question.id)).toEqual([secondId, firstId]);
    expect(reordered.questions.map((question: { number: number }) => question.number)).toEqual([1, 2]);
  });

  it("removes a middle question and closes local order and number gaps", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    group.questions.push(
      { ...questionRegistry.multiple_choice.createDefault(8).questions[0], order_index: 1 },
      { ...questionRegistry.multiple_choice.createDefault(9).questions[0], order_index: 2 },
    );
    const retainedIds = [group.questions[0].id, group.questions[2].id];
    const onChange = vi.fn();
    const view = render(<MultipleChoiceEditor group={group} onChange={onChange} />);

    fireEvent.click(within(view.container).getAllByRole("button", { name: "Remove" })[1]);
    const updated = onChange.mock.calls.at(-1)?.[0];

    expect(updated.questions.map((question: { id?: string }) => question.id)).toEqual(retainedIds);
    expect(updated.questions.map((question: { number: number }) => question.number)).toEqual([7, 8]);
    expect(updated.questions.map((question: { order_index: number }) => question.order_index)).toEqual([0, 1]);
  });
});
