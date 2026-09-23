import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { MatchingHeadingsEditor, MultipleChoiceEditor, TextCompletionEditor, VisualLabellingEditor } from "@/features/questions/editors";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { QuestionGroupInstruction, resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import type { ExamGroup } from "@/features/questions/types";

describe("question registry", () => {
  afterEach(() => vi.useRealTimers());
  const imageAsset = {
    id: crypto.randomUUID(),
    original_name: "fictional-map.png",
    mime_type: "image/png",
    file_size: 128,
    content_url: "/assets/fictional-map.png",
  };

  it.each([
    ["map_labelling", "map"],
    ["plan_labelling", "plan"],
  ] as const)("renders a Listening %s as a clean image with no question markers", (questionType, noun) => {
    const group = questionRegistry[questionType].createDefault(16, { moduleType: "LISTENING" }) as ExamGroup;
    group.id = crypto.randomUUID();
    group.image_asset_id = imageAsset.id;
    group.image_asset = imageAsset;
    const Renderer = questionRegistry[questionType].ExamRenderer;

    const view = render(<Renderer group={group} values={{}} onAnswer={vi.fn()} />);

    expect(group.config).toEqual({ options: expect.any(Array) });
    expect(screen.getByRole("img", { name: `Listening ${noun}` })).toBeInTheDocument();
    expect(view.container.querySelector(".visual-marker")).not.toBeInTheDocument();
    expect(view.container.querySelector(".visual-marker-hitarea")).not.toBeInTheDocument();
  });

  it("adds and removes Listening map questions without creating marker state", async () => {
    const group = questionRegistry.map_labelling.createDefault(16, { moduleType: "LISTENING" });
    group.image_asset_id = imageAsset.id;
    group.image_asset = imageAsset;
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(
      <QuestionGroupEditor
        initial={group}
        moduleType="LISTENING"
        nextQuestionNumber={17}
        passageBlocks={[]}
        onCancel={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "+ Add question" }));
    expect(within(view.container).getAllByRole("button", { name: "Remove" })).toHaveLength(2);
    fireEvent.click(within(view.container).getAllByRole("button", { name: "Remove" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0].config).toEqual({ options: expect.any(Array) });
    expect(onSave.mock.calls[0][0].questions).toHaveLength(1);
  });

  it("preserves Reading visual markers in the candidate renderer", () => {
    const group = questionRegistry.map_labelling.createDefault(6, { moduleType: "READING" }) as ExamGroup;
    group.id = crypto.randomUUID();
    group.image_asset_id = imageAsset.id;
    group.image_asset = imageAsset;
    const Renderer = questionRegistry.map_labelling.ExamRenderer;

    const view = render(<Renderer group={group} values={{}} onAnswer={vi.fn()} />);

    expect(view.container.querySelectorAll(".visual-marker")).toHaveLength(1);
    expect(view.container.querySelector(".visual-marker")).toHaveTextContent("6");
  });

  it("preserves Reading marker selection and placement editing", () => {
    const group = questionRegistry.plan_labelling.createDefault(9, { moduleType: "READING" });
    group.image_asset_id = imageAsset.id;
    group.image_asset = imageAsset;
    const onChange = vi.fn();
    render(<VisualLabellingEditor group={group} onChange={onChange} />);
    const hitarea = screen.getByRole("button", { name: "Place selected marker" });
    vi.spyOn(hitarea, "getBoundingClientRect").mockReturnValue({
      x: 10,
      y: 20,
      left: 10,
      top: 20,
      right: 210,
      bottom: 120,
      width: 200,
      height: 100,
      toJSON: () => ({}),
    });

    fireEvent.click(hitarea, { clientX: 170, clientY: 45 });

    const marker = onChange.mock.calls.at(-1)?.[0].config.markers[0];
    expect(marker.x).toBeCloseTo(0.8);
    expect(marker.y).toBeCloseTo(0.25);
  });

  it("creates a structured MCQ with an inline answer key", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    const options = group.questions[0].config.options as Array<{ id: string }>;
    expect(group.questions[0].number).toBe(7);
    expect(options).toHaveLength(2);
    expect(group.questions[0].answer_key.value).toBe(options[0].id);
    expect(options[0].id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("adds and removes only Listening MC options with stable IDs and sequential labels", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    group.id = crypto.randomUUID();
    group.questions[0].prompt = "Prompt must survive option edits";
    const firstId = String((group.questions[0].config.options as Array<{ id: string }>)[0].id);
    const secondId = String((group.questions[0].config.options as Array<{ id: string }>)[1].id);
    const onChange = vi.fn();
    const view = render(<MultipleChoiceEditor group={group} moduleType="LISTENING" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "+ Add option" }));
    let updated = onChange.mock.calls.at(-1)?.[0];
    const addedId = updated.questions[0].config.options[2].id;
    expect(updated.questions[0].config.options.map((option: { label: string }) => option.label)).toEqual(["A", "B", "C"]);

    view.rerender(<MultipleChoiceEditor group={updated} moduleType="LISTENING" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove option B" }));
    updated = onChange.mock.calls.at(-1)?.[0];
    expect(updated.questions[0].config.options).toEqual([
      expect.objectContaining({ id: firstId, label: "A" }),
      expect.objectContaining({ id: addedId, label: "B" }),
    ]);
    expect(updated.questions[0].config.options.some((option: { id: string }) => option.id === secondId)).toBe(false);
    expect(updated.questions[0].answer_key.value).toBe(firstId);
    expect(updated.questions[0].prompt).toBe("Prompt must survive option edits");
    expect(group.questions[0].config.options).toHaveLength(2);

    view.rerender(<MultipleChoiceEditor group={updated} moduleType="LISTENING" onChange={onChange} />);
    expect(screen.getAllByRole("button", { name: /Remove option/ })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /Remove option/ }).every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
  });

  it("clears a removed Listening MC correct answer instead of selecting a replacement", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    const options = group.questions[0].config.options as Array<{ id: string; label: string; text: string }>;
    const third = { id: crypto.randomUUID(), label: "C", text: "Third" };
    group.questions[0].config = { options: [...options, third] };
    group.questions[0].answer_key = { kind: "SINGLE_OPTION", value: third.id };
    const onChange = vi.fn();
    render(<MultipleChoiceEditor group={group} moduleType="LISTENING" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove option C" }));

    const updated = onChange.mock.calls.at(-1)?.[0];
    expect(updated.questions[0].answer_key).toEqual({ kind: "SINGLE_OPTION", value: "" });
    expect(updated.questions[0].config.options.map((option: { id: string }) => option.id)).toEqual(options.map((option) => option.id));
  });

  it("does not add option deletion controls to Reading Multiple Choice", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    render(<MultipleChoiceEditor group={group} moduleType="READING" onChange={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Remove option/ })).not.toBeInTheDocument();
  });

  it("keeps a cleared Listening MC answer local until a new valid key is selected", async () => {
    vi.useFakeTimers();
    const group = questionRegistry.multiple_choice.createDefault(7);
    group.id = crypto.randomUUID();
    group.questions[0].prompt = "Persisted prompt";
    const options = group.questions[0].config.options as Array<{ id: string; label: string; text: string }>;
    const third = { id: crypto.randomUUID(), label: "C", text: "Third" };
    group.questions[0].config = { options: [...options, third] };
    group.questions[0].answer_key = { kind: "SINGLE_OPTION", value: third.id };
    const onAutosave = vi.fn().mockResolvedValue(undefined);
    render(
      <BuilderLifecycleProvider>
        <QuestionGroupEditor initial={group} moduleType="LISTENING" nextQuestionNumber={8} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} onAutosave={onAutosave} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove option C" }));
    expect(screen.getByRole("button", { name: "Save now" })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(onAutosave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Mark A correct"));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(onAutosave).toHaveBeenCalledTimes(1);
    expect(onAutosave.mock.calls[0][0].questions[0].answer_key.value).toBe(options[0].id);
  });

  it("coalesces rapid Listening MC removal, text, and answer edits into the final autosave", async () => {
    vi.useFakeTimers();
    const group = questionRegistry.multiple_choice.createDefault(7);
    group.id = crypto.randomUUID();
    group.questions[0].prompt = "Persisted prompt";
    const options = group.questions[0].config.options as Array<{ id: string; label: string; text: string }>;
    group.questions[0].config = { options: [...options, { id: crypto.randomUUID(), label: "C", text: "Remove me" }] };
    const onAutosave = vi.fn().mockResolvedValue(undefined);
    const onSave = vi.fn();
    render(
      <BuilderLifecycleProvider>
        <QuestionGroupEditor initial={group} moduleType="LISTENING" nextQuestionNumber={8} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} onAutosave={onAutosave} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove option C" }));
    const optionText = screen.getByLabelText("Option 2 text");
    optionText.focus();
    fireEvent.change(optionText, { target: { value: "Latest B text" } });
    fireEvent.click(screen.getByLabelText("Mark B correct"));
    expect(screen.getByLabelText("Option 2 text")).toHaveValue("Latest B text");
    expect(screen.queryByRole("button", { name: "Remove option C" })).not.toBeInTheDocument();

    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    expect(onAutosave).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();
    const saved = onAutosave.mock.calls[0][0];
    expect(saved.questions[0].config.options).toHaveLength(2);
    expect(saved.questions[0].config.options[1]).toEqual(expect.objectContaining({ id: options[1].id, label: "B", text: "Latest B text" }));
    expect(saved.questions[0].answer_key.value).toBe(options[1].id);
    expect(saved.questions[0].prompt).toBe("Persisted prompt");
    expect(document.activeElement).toBe(optionText);
  });

  it("flushes the latest persisted-group edit before opening Preview", async () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    group.id = crypto.randomUUID();
    const onAutosave = vi.fn().mockResolvedValue(undefined);
    render(
      <BuilderLifecycleProvider>
        <QuestionGroupEditor initial={group} moduleType="LISTENING" nextQuestionNumber={8} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} onAutosave={onAutosave} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Newest local prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(onAutosave).toHaveBeenCalledTimes(1));
    expect(onAutosave.mock.calls[0][0].questions[0].prompt).toBe("Newest local prompt");
    expect(await screen.findByText("Newest local prompt")).toBeInTheDocument();
  });

  it("creates a new group once and does not start update autosave before identity reconciliation", async () => {
    vi.useFakeTimers();
    const group = questionRegistry.multiple_choice.createDefault(7);
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onAutosave = vi.fn().mockResolvedValue(undefined);
    render(
      <BuilderLifecycleProvider>
        <QuestionGroupEditor initial={group} moduleType="LISTENING" nextQuestionNumber={8} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} onAutosave={onAutosave} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "New group prompt" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(onAutosave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await act(async () => { await Promise.resolve(); });

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0].questions[0].prompt).toBe("New group prompt");
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
    render(<TextCompletionEditor group={group} onChange={onChange} baseQuestionNumber={11} />);
    const text = screen.getByRole("textbox", { name: "Sentence 1 text segment 1" });
    const range = document.createRange();
    range.setStart(text.firstChild!, 6);
    range.collapse(true);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
    fireEvent.mouseUp(text);
    fireEvent.click(screen.getByRole("button", { name: "+ Insert gap" }));
    const updated = onChange.mock.calls.at(-1)?.[0];
    expect(updated.config.blocks[0].segments.map((segment: { type: string; text?: string }) => segment.type)).toEqual(["TEXT", "GAP", "TEXT"]);
    expect(updated.config.blocks[0].segments[0].text).toBe("source");
    expect(updated.config.blocks[0].segments[2].text).toBe(" of income");
    expect(updated.config.blocks[0].segments[1].question_id).toBe(updated.questions[0].id);
    expect(updated.questions[0].number).toBe(11);
  });

  it("uses the module-global Q11-Q13 range and preserves it through save and reload", async () => {
    const group = questionRegistry.text_completion.createDefault(1);
    const first = group.questions[0];
    const second = { ...questionRegistry.text_completion.createDefault(2).questions[0], order_index: 1 };
    const third = { ...questionRegistry.text_completion.createDefault(3).questions[0], order_index: 2 };
    first.answer_key = { kind: "TEXT", accepted: ["first"], case_sensitive: false };
    second.answer_key = { kind: "TEXT", accepted: ["second"], case_sensitive: false };
    third.answer_key = { kind: "TEXT", accepted: ["third"], case_sensitive: false };
    group.questions = [first, second, third];
    group.config = {
      mode: "SENTENCE",
      blocks: [{
        id: crypto.randomUUID(),
        segments: [
          { id: crypto.randomUUID(), type: "TEXT", text: "One " },
          { id: crypto.randomUUID(), type: "GAP", question_id: first.id },
          { id: crypto.randomUUID(), type: "TEXT", text: " two " },
          { id: crypto.randomUUID(), type: "GAP", question_id: second.id },
          { id: crypto.randomUUID(), type: "TEXT", text: " three " },
          { id: crypto.randomUUID(), type: "GAP", question_id: third.id },
        ],
      }],
    };
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={14} baseQuestionNumber={11} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    expect(screen.getByRole("button", { name: "Gap question 11" })).toHaveTextContent("Q11");
    expect(screen.getByRole("button", { name: "Gap question 12" })).toHaveTextContent("Q12");
    expect(screen.getByRole("button", { name: "Gap question 13" })).toHaveTextContent("Q13");
    expect(screen.queryByRole("button", { name: "Gap question 1" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0][0];
    expect(saved.questions.map((question: { number: number }) => question.number)).toEqual([11, 12, 13]);
    expect(saved.questions.map((question: { id?: string }) => question.id)).toEqual([first.id, second.id, third.id]);
    expect(saved.questions.map((question: { answer_key: Record<string, unknown> }) => question.answer_key.accepted)).toEqual([["first"], ["second"], ["third"]]);

    view.unmount();
    render(<TextCompletionEditor group={saved} baseQuestionNumber={11} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Gap question 11" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gap question 13" })).toBeInTheDocument();
  });

  it("renders compact text-completion gaps inline without per-gap limit helpers", () => {
    const group = questionRegistry.text_completion.createDefault(11) as ExamGroup;
    group.id = crypto.randomUUID();
    group.questions[0].config = { max_words: 3, max_numbers: 1 };
    const second = { ...group.questions[0], id: crypto.randomUUID(), number: 12, order_index: 1 };
    group.questions.push(second);
    const block = (group.config.blocks as Array<{ segments: Array<Record<string, unknown>> }>)[0];
    block.segments.push(
      { id: crypto.randomUUID(), type: "TEXT", text: " and " },
      { id: crypto.randomUUID(), type: "GAP", question_id: second.id },
      { id: crypto.randomUUID(), type: "TEXT", text: "." },
    );
    const Renderer = questionRegistry.text_completion.ExamRenderer;
    const onAnswer = vi.fn();
    const view = render(<Renderer group={group} values={{}} onAnswer={onAnswer} />);
    expect(screen.getByLabelText("Question 11")).toBeInTheDocument();
    expect(screen.getByLabelText("Question 12")).toBeInTheDocument();
    expect(screen.getAllByRole("textbox")).toHaveLength(2);
    expect(view.container.querySelectorAll(".completion-gap-inline")).toHaveLength(2);
    expect(view.container.querySelectorAll(".text-completion-block")).toHaveLength(1);
    expect(screen.queryByText(/max 3 words/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Question 12"), { target: { value: "harbour" } });
    expect(onAnswer).toHaveBeenCalledWith(second.id, "harbour");
    expect(group.questions[0].config).toEqual({ max_words: 3, max_numbers: 1 });
  });

  it("keeps four authored completion blocks as four visual lines", () => {
    const group = questionRegistry.text_completion.createDefault(19) as ExamGroup;
    group.id = crypto.randomUUID();
    const questions = Array.from({ length: 4 }, (_, index) => ({
      ...group.questions[0],
      id: crypto.randomUUID(),
      number: 19 + index,
      order_index: index,
    }));
    group.questions = questions;
    group.config = {
      mode: "SENTENCE",
      blocks: questions.map((question, index) => ({
        id: crypto.randomUUID(),
        segments: [
          { id: crypto.randomUUID(), type: "TEXT", text: `Authored line ${index + 1} before ` },
          { id: crypto.randomUUID(), type: "GAP", question_id: question.id },
          { id: crypto.randomUUID(), type: "TEXT", text: ` after line ${index + 1}.` },
        ],
      })),
    };

    const Renderer = questionRegistry.text_completion.ExamRenderer;
    const view = render(<Renderer group={group} values={{}} onAnswer={vi.fn()} />);
    const lines = [...view.container.querySelectorAll(".text-completion-line")];

    expect(lines).toHaveLength(4);
    expect(lines.map((line) => line.textContent)).toEqual([
      "Authored line 1 before 19 after line 1.",
      "Authored line 2 before 20 after line 2.",
      "Authored line 3 before 21 after line 3.",
      "Authored line 4 before 22 after line 4.",
    ]);
    expect(lines.every((line) => line.querySelector(".completion-gap-inline input"))).toBe(true);
    expect(view.container.querySelectorAll(".completion-gap-inline")).toHaveLength(4);
  });

  it("keeps multiline completion instructions author-controlled as limits change", async () => {
    const group = questionRegistry.text_completion.createDefault(11);
    group.instruction = "Complete the notes below.\nWrite your answers in the gaps.";
    const onSave = vi.fn().mockResolvedValue(undefined);
    const view = render(<QuestionGroupEditor initial={group} nextQuestionNumber={12} passageBlocks={[]} onCancel={vi.fn()} onSave={onSave} />);

    const instructions = screen.getByRole("textbox", { name: "Candidate instructions" });
    expect(instructions.tagName).toBe("TEXTAREA");
    fireEvent.change(screen.getByLabelText("Maximum words"), { target: { value: "4" } });
    expect(instructions).toHaveValue("Complete the notes below.\nWrite your answers in the gaps.");

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(view.container.querySelector(".question-group-instruction-text")).toHaveTextContent("Complete the notes below. Write your answers in the gaps.");
    fireEvent.click(screen.getByRole("button", { name: "Back to edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0].instruction).toBe("Complete the notes below.\nWrite your answers in the gaps.");
  });

  it("preserves the single-line instruction editor for non-completion groups", () => {
    const group = questionRegistry.true_false_not_given.createDefault(1);
    render(<QuestionGroupEditor initial={group} nextQuestionNumber={2} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "Group instruction" }).tagName).toBe("INPUT");
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
