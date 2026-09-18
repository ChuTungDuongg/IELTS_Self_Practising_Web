import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { MatchingHeadingsEditor, MultipleChoiceEditor } from "@/features/questions/editors";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
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
