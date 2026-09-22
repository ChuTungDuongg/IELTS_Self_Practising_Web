import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup, QuestionGroupModel } from "@/features/questions/types";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";

type TestNoteSegment =
  | { id: string; type: "TEXT"; text: string }
  | { id: string; type: "GAP"; question_id: string };

type TestNoteBlock = {
  id: string;
  style: "HEADING" | "TEXT" | "BULLET" | "EXAMPLE";
  indent: number;
  segments: TestNoteSegment[];
};

type TestNoteLayout = {
  kind: "NOTE";
  title?: string;
  columns: [];
  rows: [];
  nodes: [];
  blocks: TestNoteBlock[];
};

function noteGroup(): QuestionGroupModel {
  const firstId = crypto.randomUUID();
  const secondId = crypto.randomUUID();
  return {
    id: crypto.randomUUID(),
    question_type: "note_completion",
    instruction: "Complete the notes.",
    order_index: 0,
    config: {
      layout: {
        kind: "NOTE",
        title: "HIRING A PUBLIC ROOM",
        columns: [],
        rows: [],
        nodes: [],
        blocks: [
          {
            id: crypto.randomUUID(),
            style: "HEADING",
            indent: 0,
            segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "Room and cost" }],
          },
          {
            id: crypto.randomUUID(),
            style: "BULLET",
            indent: 1,
            segments: [
              { id: crypto.randomUUID(), type: "TEXT", text: "the " },
              { id: crypto.randomUUID(), type: "GAP", question_id: firstId },
              { id: crypto.randomUUID(), type: "TEXT", text: " Room – seats 100 and costs £" },
              { id: crypto.randomUUID(), type: "GAP", question_id: secondId },
            ],
          },
          {
            id: crypto.randomUUID(),
            style: "EXAMPLE",
            indent: 0,
            segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "Example" }],
          },
        ],
      } satisfies TestNoteLayout,
    },
    questions: [
      {
        id: firstId,
        number: 11,
        prompt: "Note gap",
        config: { max_words: 2, max_numbers: 1 },
        answer_key: { kind: "TEXT", accepted: ["small"], case_sensitive: false },
        order_index: 0,
      },
      {
        id: secondId,
        number: 12,
        prompt: "Note gap",
        config: { max_words: 1, max_numbers: 0 },
        answer_key: { kind: "TEXT", accepted: ["75"], case_sensitive: false },
        order_index: 1,
      },
    ],
  };
}

function EditorHarness({
  initial = questionRegistry.note_completion.createDefault(11),
  baseQuestionNumber = 11,
}: { initial?: QuestionGroupModel; baseQuestionNumber?: number }) {
  const [group, setGroup] = useState(initial);
  const Editor = questionRegistry.note_completion.BuilderEditor;
  return <><Editor group={group} onChange={setGroup} baseQuestionNumber={baseQuestionNumber} /><output data-testid="note-state">{JSON.stringify(group)}</output></>;
}

function currentGroup(): QuestionGroupModel {
  return JSON.parse(screen.getByTestId("note-state").textContent ?? "{}") as QuestionGroupModel;
}

function currentLayout(): TestNoteLayout {
  return currentGroup().config.layout as TestNoteLayout;
}

function typeEditable(editor: HTMLElement, text: string) {
  editor.textContent = text;
  fireEvent.input(editor);
}

describe("note completion", () => {
  it("starts as one blank text block with zero questions and hides generic Add question", () => {
    const group = questionRegistry.note_completion.createDefault(11);
    const layout = group.config.layout as TestNoteLayout;

    expect(group.questions).toEqual([]);
    expect(layout.title).toBe("");
    expect(layout.blocks).toHaveLength(1);
    expect(layout.blocks[0]).toMatchObject({ style: "TEXT", indent: 0 });
    expect(layout.blocks[0].segments).toMatchObject([{ type: "TEXT", text: "" }]);

    render(<QuestionGroupEditor initial={group} nextQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "+ Add question" })).not.toBeInTheDocument();
  });

  it("keeps autosave disabled while a Note block is empty", () => {
    const group = questionRegistry.note_completion.createDefault(11);
    group.id = crypto.randomUUID();
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} onAutosave={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Save now" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Note blocks cannot be empty when saved.");
  });

  it("renders the optional title and mixed text gaps inline for Candidate", () => {
    const group = noteGroup() as ExamGroup;
    const onAnswer = vi.fn();
    const Renderer = questionRegistry.note_completion.ExamRenderer;
    const view = render(<Renderer group={group} values={{}} onAnswer={onAnswer} />);

    expect(screen.getByText("HIRING A PUBLIC ROOM")).toHaveClass("note-completion-title");
    const bullet = screen.getByText(/Room – seats 100 and costs/).closest(".note-completion-block");
    expect(bullet).toHaveTextContent("the 11 Room – seats 100 and costs £12");
    expect(within(bullet as HTMLElement).getByLabelText("Question 11")).toBeInTheDocument();
    expect(view.container.querySelectorAll(".note-completion-answer")).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("Question 11"), { target: { value: "small" } });
    expect(onAnswer).toHaveBeenCalledWith(group.questions[0].id, "small");
  });

  it("uses the same Note renderer in Review", () => {
    const group = noteGroup() as ExamGroup;
    const Review = questionRegistry.note_completion.ReviewRenderer;
    render(<Review group={group} values={{ [group.questions[0].id]: "small" }} disabled />);

    expect(screen.getByText("HIRING A PUBLIC ROOM")).toBeInTheDocument();
    expect(screen.getByLabelText("Question 11")).toHaveValue("small");
  });

  it("renders heading, bullet, example, and semantic indentation", () => {
    const group = noteGroup() as ExamGroup;
    const Renderer = questionRegistry.note_completion.ExamRenderer;
    const view = render(<Renderer group={group} values={{}} />);

    expect(screen.getByText("Room and cost").closest(".note-completion-block")).toHaveClass("note-style-heading");
    expect(view.container.querySelector(".note-style-bullet .note-completion-marker")).toHaveTextContent("•");
    expect(screen.getByText("Example").closest(".note-completion-block")).toHaveClass("note-style-example");
    expect(view.container.querySelector(".note-indent-1")).toBeInTheDocument();
  });

  it("does not render an empty note title", () => {
    const group = noteGroup() as ExamGroup;
    (group.config.layout as TestNoteLayout).title = "";
    const Renderer = questionRegistry.note_completion.ExamRenderer;
    const view = render(<Renderer group={group} values={{}} />);
    expect(view.container.querySelector(".note-completion-title")).not.toBeInTheDocument();
  });

  it("normalizes display numbers by block and segment order in Builder Preview", () => {
    const group = noteGroup();
    group.questions = [
      { ...group.questions[1], number: 11, order_index: 0 },
      { ...group.questions[0], number: 12, order_index: 1 },
    ];
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    const inputs = screen.getAllByRole("textbox", { name: /Question/ });
    expect(inputs.map((input) => input.getAttribute("aria-label"))).toEqual(["Question 11", "Question 12"]);
  });

  it("accepts a valid Note layout for saving and passes its canonical shape", async () => {
    const group = noteGroup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={13} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    const save = screen.getByRole("button", { name: "Save now" });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect((onSave.mock.calls[0][0].config.layout as TestNoteLayout).blocks).toHaveLength(3);
  });

  it("converts a typed gap shortcut inside one text segment and selects its inspector", () => {
    render(<EditorHarness />);
    typeEditable(screen.getByRole("textbox", { name: "Note block 1 text segment 1" }), "the {{gap}} Room");

    const group = currentGroup();
    expect(currentLayout().blocks[0].segments.map((segment) => segment.type)).toEqual(["TEXT", "GAP", "TEXT"]);
    expect(currentLayout().blocks[0].segments).toMatchObject([
      { type: "TEXT", text: "the " },
      { type: "GAP", question_id: group.questions[0].id },
      { type: "TEXT", text: " Room" },
    ]);
    expect(group.questions[0]).toMatchObject({
      number: 11,
      order_index: 0,
      config: { max_words: 2, max_numbers: 1 },
      answer_key: { kind: "TEXT", accepted: ["answer"], case_sensitive: false },
    });
    expect(JSON.stringify(group)).not.toContain("{{gap}}");
    expect(screen.getByLabelText("Question 11 note gap inspector")).toBeInTheDocument();
  });

  it("keeps the inspector selected and continues typing after a real shortcut key sequence", () => {
    render(<EditorHarness />);
    const original = screen.getByRole("textbox", { name: "Note block 1 text segment 1" });
    original.textContent = "the {{gap}}";
    fireEvent.input(original);
    fireEvent.keyUp(original, { key: "}" });

    const trailing = screen.getByRole("textbox", { name: "Note block 1 text segment 3" });
    expect(trailing).toHaveFocus();
    expect(screen.getByLabelText("Question 11 note gap inspector")).toBeInTheDocument();

    typeEditable(trailing, " Room");
    expect(currentLayout().blocks[0].segments).toMatchObject([
      { type: "TEXT", text: "the " },
      { type: "GAP" },
      { type: "TEXT", text: " Room" },
    ]);
  });

  it("converts two pasted gap shortcuts left-to-right into distinct stable questions", () => {
    render(<EditorHarness />);
    typeEditable(screen.getByRole("textbox", { name: "Note block 1 text segment 1" }), "£{{gap}} plus {{gap}} deposit");

    const group = currentGroup();
    const segments = currentLayout().blocks[0].segments;
    expect(segments.map((segment) => segment.type)).toEqual(["TEXT", "GAP", "TEXT", "GAP", "TEXT"]);
    expect(group.questions).toHaveLength(2);
    expect(new Set(group.questions.map((question) => question.id)).size).toBe(2);
    expect(segments.filter((segment) => segment.type === "GAP").map((segment) => segment.question_id)).toEqual(group.questions.map((question) => question.id));
    expect(JSON.stringify(group)).not.toContain("{{gap}}");
  });

  it("preserves an empty text boundary between adjacent gap shortcuts", () => {
    render(<EditorHarness />);
    typeEditable(screen.getByRole("textbox", { name: "Note block 1 text segment 1" }), "A{{gap}}{{gap}}B");

    expect(currentLayout().blocks[0].segments).toMatchObject([
      { type: "TEXT", text: "A" },
      { type: "GAP" },
      { type: "TEXT", text: "" },
      { type: "GAP" },
      { type: "TEXT", text: "B" },
    ]);
    expect(currentGroup().questions.map((question) => question.number)).toEqual([11, 12]);
  });

  it("edits surrounding text without recreating existing gap, question, or answer key", () => {
    const initial = noteGroup();
    const layout = initial.config.layout as TestNoteLayout;
    const questionId = initial.questions[0].id;
    const answerKey = initial.questions[0].answer_key;
    const gapId = layout.blocks[1].segments.find((segment) => segment.type === "GAP")!.id;
    render(<EditorHarness initial={initial} />);

    typeEditable(screen.getByRole("textbox", { name: "Note block 2 text segment 1" }), "a very small ");

    const group = currentGroup();
    expect(group.questions.find((question) => question.id === questionId)?.answer_key).toEqual(answerKey);
    expect(currentLayout().blocks[1].segments.find((segment) => segment.type === "GAP")?.id).toBe(gapId);
  });

  it("inserts an explicit gap at the active caret", () => {
    render(<EditorHarness />);
    const editor = screen.getByRole("textbox", { name: "Note block 1 text segment 1" });
    typeEditable(editor, "room name");
    const range = document.createRange();
    range.setStart(editor.firstChild!, 4);
    range.collapse(true);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.keyUp(editor, { key: "ArrowLeft" });
    fireEvent.click(screen.getByRole("button", { name: "+ Insert gap" }));

    expect(currentLayout().blocks[0].segments).toMatchObject([
      { type: "TEXT", text: "room" },
      { type: "GAP" },
      { type: "TEXT", text: " name" },
    ]);
  });

  it("drags a gap within a block without changing its UUID or answer key", () => {
    const initial = noteGroup();
    const questionId = initial.questions[1].id!;
    const answerKey = initial.questions[1].answer_key;
    render(<EditorHarness initial={initial} />);
    const target = screen.getByRole("textbox", { name: "Note block 2 text segment 1" });
    const range = document.createRange();
    range.setStart(target.firstChild!, 0);
    range.collapse(true);
    Object.defineProperty(document, "caretRangeFromPoint", { configurable: true, value: vi.fn(() => range) });
    let transferred = "";
    const dataTransfer = { effectAllowed: "none", dropEffect: "none", setData: vi.fn((_type: string, value: string) => { transferred = value; }), getData: vi.fn(() => transferred) };

    fireEvent.dragStart(screen.getByRole("button", { name: "Note gap question 12" }), { dataTransfer });
    fireEvent.dragOver(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });
    fireEvent.drop(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });

    const group = currentGroup();
    expect(currentLayout().blocks[1].segments.find((segment) => segment.type === "GAP")?.question_id).toBe(questionId);
    expect(group.questions.find((question) => question.id === questionId)?.answer_key).toEqual(answerKey);
    Reflect.deleteProperty(document, "caretRangeFromPoint");
  });

  it("drags a gap to another block while preserving its question identity", () => {
    const initial = noteGroup();
    const questionId = initial.questions[0].id!;
    const gapId = (initial.config.layout as TestNoteLayout).blocks[1].segments.find((segment) => segment.type === "GAP")!.id;
    render(<EditorHarness initial={initial} />);
    const target = screen.getByRole("textbox", { name: "Note block 3 text segment 1" });
    const range = document.createRange();
    range.setStart(target.firstChild!, 0);
    range.collapse(true);
    Object.defineProperty(document, "caretRangeFromPoint", { configurable: true, value: vi.fn(() => range) });
    const dataTransfer = { effectAllowed: "none", dropEffect: "none", setData: vi.fn(), getData: vi.fn(() => gapId) };

    fireEvent.dragStart(screen.getByRole("button", { name: "Note gap question 11" }), { dataTransfer });
    fireEvent.dragOver(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });
    fireEvent.drop(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });

    const group = currentGroup();
    expect(currentLayout().blocks[2].segments.some((segment) => segment.id === gapId && segment.type === "GAP" && segment.question_id === questionId)).toBe(true);
    expect(group.questions.some((question) => question.id === questionId)).toBe(true);
    Reflect.deleteProperty(document, "caretRangeFromPoint");
  });

  it("preserves all surrounding text when a gap is dragged out and back", () => {
    const initial = noteGroup();
    const originalText = (initial.config.layout as TestNoteLayout).blocks.map((block) => (
      block.segments.filter((segment) => segment.type === "TEXT").map((segment) => segment.text).join("")
    ));
    const movedGapId = (initial.config.layout as TestNoteLayout).blocks[1].segments.find((segment) => segment.type === "GAP")!.id;
    render(<EditorHarness initial={initial} />);
    let target = screen.getByRole("textbox", { name: "Note block 3 text segment 1" });
    let range = document.createRange();
    range.setStart(target.firstChild!, 3);
    range.collapse(true);
    Object.defineProperty(document, "caretRangeFromPoint", { configurable: true, value: vi.fn(() => range) });
    const dataTransfer = { effectAllowed: "none", dropEffect: "none", setData: vi.fn(), getData: vi.fn(() => movedGapId) };

    fireEvent.dragStart(screen.getByRole("button", { name: "Note gap question 11" }), { dataTransfer });
    fireEvent.dragOver(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });
    fireEvent.drop(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });

    target = screen.getByRole("textbox", { name: "Note block 2 text segment 1" });
    range = document.createRange();
    range.setStart(target.firstChild!, 4);
    range.collapse(true);
    Object.defineProperty(document, "caretRangeFromPoint", { configurable: true, value: vi.fn(() => range) });
    fireEvent.dragStart(screen.getByRole("button", { name: "Note gap question 12" }), { dataTransfer });
    fireEvent.dragOver(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });
    fireEvent.drop(target.closest("[data-note-block]")!, { clientX: 10, clientY: 10, dataTransfer });

    expect(currentLayout().blocks.map((block) => (
      block.segments.filter((segment) => segment.type === "TEXT").map((segment) => segment.text).join("")
    ))).toEqual(originalText);
    expect(currentLayout().blocks[1].segments.some((segment) => segment.id === movedGapId)).toBe(true);
    Reflect.deleteProperty(document, "caretRangeFromPoint");
  });

  it("changes block style and indent without changing linked gaps or questions", () => {
    const initial = noteGroup();
    const questionIds = initial.questions.map((question) => question.id);
    const gapIds = (initial.config.layout as TestNoteLayout).blocks[1].segments.filter((segment) => segment.type === "GAP").map((segment) => segment.id);
    render(<EditorHarness initial={initial} />);

    fireEvent.change(screen.getByLabelText("Block 2 style"), { target: { value: "HEADING" } });
    fireEvent.click(screen.getByRole("button", { name: "Increase block 2 indent" }));

    expect(currentLayout().blocks[1]).toMatchObject({ style: "HEADING", indent: 2 });
    expect(currentLayout().blocks[1].segments.filter((segment) => segment.type === "GAP").map((segment) => segment.id)).toEqual(gapIds);
    expect(currentGroup().questions.map((question) => question.id)).toEqual(questionIds);
  });

  it("renumbers moved gaps after a temporarily blank block is filled", () => {
    const initial = noteGroup();
    const layout = initial.config.layout as TestNoteLayout;
    const gapBlock = layout.blocks[1];
    layout.blocks = [
      { ...gapBlock, id: crypto.randomUUID(), segments: gapBlock.segments.slice(0, 2) },
      { ...gapBlock, id: crypto.randomUUID(), segments: gapBlock.segments.slice(2) },
      { id: crypto.randomUUID(), style: "TEXT", indent: 0, segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "" }] },
    ];
    render(<EditorHarness initial={initial} />);

    fireEvent.click(screen.getByRole("button", { name: "Move block 2 up" }));
    typeEditable(screen.getByRole("textbox", { name: "Note block 3 text segment 1" }), "Additional detail");

    expect(screen.getAllByRole("button", { name: /Note gap question/ }).map((button) => button.getAttribute("aria-label"))).toEqual([
      "Note gap question 11",
      "Note gap question 12",
    ]);
    expect(currentGroup().questions.map((question) => question.number)).toEqual([11, 12]);
    expect(currentGroup().questions.map((question) => question.id)).toEqual([
      initial.questions[1].id,
      initial.questions[0].id,
    ]);
  });

  it("creates the natural next block on Enter", () => {
    const initial = noteGroup();
    render(<EditorHarness initial={initial} />);
    const editor = screen.getByRole("textbox", { name: "Note block 2 text segment 1" });
    editor.focus();
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.keyDown(editor, { key: "Enter" });

    expect(currentLayout().blocks).toHaveLength(4);
    expect(currentLayout().blocks[2]).toMatchObject({ style: "BULLET", indent: 1 });
  });

  it("removes one selected gap and only its linked question after confirmation", () => {
    const initial = noteGroup();
    const retainedId = initial.questions[1].id;
    render(<EditorHarness initial={initial} />);
    fireEvent.click(screen.getByRole("button", { name: "Note gap question 11" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove gap" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove gap" }));

    expect(currentGroup().questions.map((question) => question.id)).toEqual([retainedId]);
    expect(currentLayout().blocks.flatMap((block) => block.segments).filter((segment) => segment.type === "GAP")).toHaveLength(1);
  });

  it("confirms question numbers before removing a block with linked gaps", () => {
    render(<EditorHarness initial={noteGroup()} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete block 2" }));

    expect(screen.getByText(/Q11 and Q12/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove block" }));
    expect(currentGroup().questions).toEqual([]);
    expect(currentLayout().blocks).toHaveLength(2);
  });

  it("removes every linked question in a block and renumbers survivors from the supplied base", () => {
    const initial = noteGroup();
    const survivingId = crypto.randomUUID();
    initial.questions = [
      { ...initial.questions[0], number: 20 },
      { ...initial.questions[1], number: 21 },
      {
        id: survivingId,
        number: 22,
        prompt: "Note gap",
        config: { max_words: 1, max_numbers: 0 },
        answer_key: { kind: "TEXT", accepted: ["example"], case_sensitive: false },
        order_index: 2,
      },
    ];
    (initial.config.layout as TestNoteLayout).blocks[2].segments.push(
      { id: crypto.randomUUID(), type: "GAP", question_id: survivingId },
      { id: crypto.randomUUID(), type: "TEXT", text: " detail" },
    );
    render(<EditorHarness initial={initial} baseQuestionNumber={20} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete block 2" }));
    expect(screen.getByText(/Q20 and Q21/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove block" }));

    expect(currentGroup().questions).toMatchObject([{ id: survivingId, number: 20, order_index: 0 }]);
    expect(screen.getByRole("button", { name: "Note gap question 20" })).toBeInTheDocument();
  });
});
