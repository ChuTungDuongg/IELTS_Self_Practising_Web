import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { TableCompletionEditor } from "@/features/questions/table-completion-editor";
import type { ExamGroup, QuestionGroupModel, TableCompletionLayout } from "@/features/questions/types";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";

function tableGroup(): QuestionGroupModel {
  const group = questionRegistry.table_completion.createDefault(30);
  group.id = crypto.randomUUID();
  group.questions[0].answer_key = { kind: "TEXT", accepted: ["sunshade"], case_sensitive: false };
  return group;
}

function EditorHarness({ initial = tableGroup() }: { initial?: QuestionGroupModel }) {
  const [group, setGroup] = useState(initial);
  return <><TableCompletionEditor group={group} onChange={setGroup} baseQuestionNumber={30} /><output data-testid="state">{JSON.stringify(group)}</output></>;
}

function currentGroup(): QuestionGroupModel {
  return JSON.parse(screen.getByTestId("state").textContent ?? "{}") as QuestionGroupModel;
}

function layoutOf(group = currentGroup()): TableCompletionLayout {
  return group.config.layout as TableCompletionLayout;
}

describe("table completion", () => {
  it("stores an optional title and renders it in Builder Preview", async () => {
    const group = tableGroup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={31} baseQuestionNumber={30} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    expect(screen.queryByRole("button", { name: "+ Add question" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Table title"), { target: { value: "  GEO-ENGINEERING PROJECTS  " } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(screen.getByText("GEO-ENGINEERING PROJECTS")).toHaveClass("table-completion-title");
    fireEvent.click(screen.getByRole("button", { name: "Back to edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save now" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect((onSave.mock.calls[0][0].config.layout as TableCompletionLayout).title).toBe("GEO-ENGINEERING PROJECTS");
  });

  it("renders title and mixed TEXT + GAP + TEXT inline for Candidate", () => {
    const group = tableGroup() as ExamGroup;
    const layout = group.config.layout as TableCompletionLayout;
    layout.title = "GEO-ENGINEERING PROJECTS";
    const secondCell = layout.rows[0].cells[1];
    secondCell.segments = [
      { id: crypto.randomUUID(), type: "TEXT", text: "to create a " },
      { id: crypto.randomUUID(), type: "GAP", question_id: group.questions[0].id },
      { id: crypto.randomUUID(), type: "TEXT", text: " that would reduce the light" },
    ];
    const onAnswer = vi.fn();
    const Renderer = questionRegistry.table_completion.ExamRenderer;
    const view = render(<Renderer group={group} values={{}} onAnswer={onAnswer} />);

    const cell = view.container.querySelectorAll("td")[1];
    expect(screen.getByText("GEO-ENGINEERING PROJECTS")).toBeInTheDocument();
    expect(cell).toHaveTextContent("to create a 30 that would reduce the light");
    expect(within(cell).getByLabelText("Question 30")).toBeInTheDocument();
    expect(view.container.querySelectorAll(".table-completion-answer")).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Question 30"), { target: { value: "sunshade" } });
    expect(onAnswer).toHaveBeenCalledWith(group.questions[0].id, "sunshade");
  });

  it("uses the same title and inline table renderer for Review", () => {
    const group = tableGroup() as ExamGroup;
    (group.config.layout as TableCompletionLayout).title = "Review table title";
    const Review = questionRegistry.table_completion.ReviewRenderer;
    const view = render(<Review group={group} values={{ [group.questions[0].id]: "sunshade" }} disabled />);

    expect(screen.getByText("Review table title")).toBeInTheDocument();
    expect(screen.getByLabelText("Question 30")).toHaveValue("sunshade");
    expect(view.container.querySelector(".table-completion-candidate-table")).toBeInTheDocument();
  });

  it("inserts a question and GAP segment together at the selected text caret", () => {
    render(<EditorHarness />);
    const text = screen.getByLabelText("Row 1 column 1 text segment 1") as HTMLInputElement;
    fireEvent.change(text, { target: { value: "Type cell text" } });
    text.setSelectionRange(4, 4);
    fireEvent.select(text);
    fireEvent.click(screen.getByRole("button", { name: "+ Insert gap" }));

    const group = currentGroup();
    const segments = layoutOf(group).rows[0].cells[0].segments;
    expect(segments.map((segment) => segment.type)).toEqual(["TEXT", "GAP", "TEXT"]);
    expect(segments[0]).toMatchObject({ type: "TEXT", text: "Type" });
    expect(segments[2]).toMatchObject({ type: "TEXT", text: " cell text" });
    expect(segments[1]).toMatchObject({ type: "GAP", question_id: group.questions[1].id });
    expect(group.questions[1]).toMatchObject({
      number: 31,
      order_index: 1,
      answer_key: { kind: "TEXT", accepted: [], case_sensitive: false },
    });
    expect(screen.getByLabelText("Question 31 table gap inspector")).toBeInTheDocument();
  });

  it("navigates table gaps in row and cell order without changing layout", () => {
    const group = tableGroup();
    const layout = layoutOf(group);
    const second = { ...questionRegistry.table_completion.createDefault(31).questions[0], order_index: 1 };
    const firstGap = layout.rows[0].cells[1].segments.find((segment) => segment.type === "GAP")!;
    layout.rows[0].cells[0].segments.push({ id: crypto.randomUUID(), type: "GAP", question_id: group.questions[0].id! });
    if (firstGap.type === "GAP") firstGap.question_id = second.id!;
    group.questions = [second, group.questions[0]];
    const originalLayout = JSON.stringify(layout);
    render(<EditorHarness initial={group} />);

    expect(screen.getByText("Q30 · 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "← Previous" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    expect(screen.getByText("Q31 · 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Correct answer" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Next →" })).toBeDisabled();
    expect(JSON.stringify(layoutOf())).toBe(originalLayout);
    fireEvent.click(screen.getByRole("button", { name: "← Previous" }));
    expect(screen.getByText("Q30 · 1 of 2")).toBeInTheDocument();
  });

  it("drags a gap to another cell without changing its question UUID or answer key", () => {
    render(<EditorHarness />);
    const before = currentGroup();
    const questionId = before.questions[0].id;
    const answerKey = before.questions[0].answer_key;
    let transferred = "";
    const dataTransfer = {
      effectAllowed: "none",
      dropEffect: "none",
      setData: vi.fn((_type: string, value: string) => { transferred = value; }),
      getData: vi.fn(() => transferred),
    };
    const gap = screen.getByRole("button", { name: "Table gap question 30" });
    const target = screen.getByRole("button", { name: "Move gap to row 1, column 1, position 1" });

    fireEvent.dragStart(gap, { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });

    const after = currentGroup();
    const firstCellGap = layoutOf(after).rows[0].cells[0].segments.find((segment) => segment.type === "GAP");
    expect(firstCellGap).toMatchObject({ question_id: questionId });
    expect(after.questions[0].id).toBe(questionId);
    expect(after.questions[0].number).toBe(30);
    expect(after.questions[0].answer_key).toEqual(answerKey);
  });

  it("removes the selected gap and linked question", () => {
    render(<EditorHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Table gap question 30" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove gap" }));

    expect(currentGroup().questions).toHaveLength(0);
    expect(layoutOf().rows.flatMap((row) => row.cells).flatMap((cell) => cell.segments).some((segment) => segment.type === "GAP")).toBe(false);
  });

  it("removes all linked questions with a deleted row", () => {
    const group = tableGroup();
    const layout = group.config.layout as TableCompletionLayout;
    const second = questionRegistry.table_completion.createDefault(31).questions[0];
    second.order_index = 1;
    group.questions.push(second);
    layout.rows.push({
      id: crypto.randomUUID(),
      cells: [
        { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "GAP", question_id: second.id! }] },
        { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "second row" }] },
      ],
    });
    render(<EditorHarness initial={group} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Remove row" })[1]);

    expect(currentGroup().questions.map((question) => question.id)).toEqual([group.questions[0].id]);
    expect(layoutOf().rows).toHaveLength(1);
  });

  it("removes all linked questions with a deleted column", () => {
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Remove column 2" }));

    expect(currentGroup().questions).toHaveLength(0);
    expect(layoutOf().columns).toHaveLength(1);
    expect(layoutOf().rows[0].cells).toHaveLength(1);
  });

  it("keeps Add row and Add column as layout-only operations", () => {
    render(<EditorHarness />);
    const questionId = currentGroup().questions[0].id;

    fireEvent.click(screen.getByRole("button", { name: "+ Add row" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add column" }));

    const group = currentGroup();
    const layout = layoutOf(group);
    expect(layout.rows).toHaveLength(2);
    expect(layout.columns).toHaveLength(3);
    expect(layout.rows.every((row) => row.cells.length === 3)).toBe(true);
    expect(group.questions.map((question) => question.id)).toEqual([questionId]);
    expect(layout.rows[1].cells.every((cell) => cell.segments[0].type === "TEXT")).toBe(true);
  });

  it("does not render an empty title element", () => {
    const group = tableGroup() as ExamGroup;
    const Renderer = questionRegistry.table_completion.ExamRenderer;
    const view = render(<Renderer group={group} values={{}} />);
    expect(view.container.querySelector("figcaption")).not.toBeInTheDocument();
  });
});
