import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import type { QuestionGroupModel } from "@/features/questions/types";
import { BuilderAutosaveStatus, BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { QuestionGroupEditor } from "@/features/test-builder/question-group-editor";
import { VersionActions } from "@/features/test-builder/version-actions";
import type { BuilderVersion } from "@/lib/api/builder";
import { validateVersion } from "@/lib/api/tests";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, validateVersion: vi.fn() };
});

function persisted(group: QuestionGroupModel): QuestionGroupModel {
  return { ...group, id: crypto.randomUUID(), revision: 1, questions: group.questions.map((question) => ({ ...question, prompt: "Fictional prompt" })) };
}

function version(group: QuestionGroupModel): BuilderVersion {
  return { id: crypto.randomUUID(), test_id: crypto.randomUUID(), test_title: "Fictional draft", version_number: 1, status: "DRAFT", modules: [{ id: crypto.randomUUID(), revision: 1, module_type: "READING", title: "Reading", recommended_duration_seconds: 3600, audio_asset: null, listening_parts: [], writing_tasks: [], passages: [{ id: crypto.randomUUID(), revision: 1, title: "Fictional passage", order_index: 0, blocks: [], question_groups: [group as never] }] }] };
}

function setup(group: QuestionGroupModel, save = vi.fn().mockImplementation(async (value: QuestionGroupModel) => ({ ...value, revision: 2 })), withActions = false) {
  const builderVersion = version(group);
  render(<BuilderLifecycleProvider>
    <BuilderAutosaveStatus />
    {withActions ? <VersionActions testId={builderVersion.test_id} version={builderVersion} /> : null}
    <QuestionGroupEditor initial={group} nextQuestionNumber={group.questions[0].number + 1} passageBlocks={[]} onCancel={vi.fn()} onSave={vi.fn()} onAutosave={save} />
  </BuilderLifecycleProvider>);
  return save;
}

describe("draft answer-key autosave", () => {
  afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

  it("saves an instruction edit and one MCQ answer while its sibling key stays empty", async () => {
    vi.useFakeTimers();
    const group = persisted(questionRegistry.multiple_choice.createDefault(1));
    group.questions[0].answer_key = { kind: "SINGLE_OPTION", value: "" };
    group.questions.push({ ...group.questions[0], id: crypto.randomUUID(), number: 2, order_index: 1, answer_key: { kind: "SINGLE_OPTION", value: "" } });
    const save = setup(group);
    fireEvent.change(screen.getByLabelText("Group instruction"), { target: { value: "Revised instruction" } });
    expect(screen.getAllByText("Unsaved changes").length).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("radio", { name: "Mark A correct" })[0]);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[1][0].questions[1].answer_key.value).toBe("");
  });

  it("saves a formatting edit on an imported group with an empty text key", async () => {
    vi.useFakeTimers();
    const group = persisted(questionRegistry.short_answer.createDefault(1));
    group.questions[0].answer_key = { kind: "TEXT", accepted: [], case_sensitive: false };
    const save = setup(group);
    fireEvent.change(screen.getByLabelText("Group instruction"), { target: { value: "Use two words" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].questions[0].answer_key.accepted).toEqual([]);
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Correct answer"), { target: { value: "fictional" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Correct answer"), { target: { value: "" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save.mock.calls[2][0].questions[0].answer_key.accepted).toEqual([""]);
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0);
  });

  it("saves zero, one, and two official choices for a grouped multi-select draft", async () => {
    vi.useFakeTimers();
    const group = persisted(questionRegistry.multiple_choice_multiple.createDefault(13));
    const save = setup(group);
    fireEvent.change(screen.getByLabelText("Group instruction"), { target: { value: "Choose two fictional places" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save.mock.calls[0][0].questions[0].answer_key.values).toEqual([]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Mark A correct" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save.mock.calls[1][0].questions[0].answer_key.values).toHaveLength(1);
    expect(screen.queryByText("Unsaved — fix validation issues")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Mark B correct" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save.mock.calls[2][0].questions[0].answer_key.values).toHaveLength(2);
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0);
    expect(screen.getByRole("checkbox", { name: "Mark C correct" })).toBeDisabled();
  });

  it("blocks a duplicate option label with a local explanation", async () => {
    vi.useFakeTimers();
    const save = setup(persisted(questionRegistry.multiple_choice.createDefault(1)));
    fireEvent.change(screen.getByLabelText("Option 2 label"), { target: { value: "A" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Option labels must be unique.");
    expect(screen.getByRole("button", { name: "Save now" })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(save).not.toHaveBeenCalled();
  });

  it("flushes an incomplete key before reaching contextual version validation", async () => {
    const group = persisted(questionRegistry.multiple_choice.createDefault(1));
    group.questions[0].answer_key = { kind: "SINGLE_OPTION", value: "" };
    const save = vi.fn().mockImplementation(async (value: QuestionGroupModel) => ({ ...value, revision: 2 }));
    vi.mocked(validateVersion).mockResolvedValue({ valid: false, errors: [{ path: "reading.questions.1", message: "Answer key is incomplete." }], warnings: [] });
    setup(group, save, true);
    fireEvent.change(screen.getByLabelText("Group instruction"), { target: { value: "Revised instruction" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(validateVersion).toHaveBeenCalledOnce());
    expect(save).toHaveBeenCalledOnce();
    expect(save.mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(validateVersion).mock.invocationCallOrder[0]);
    expect(screen.getByText("Answer key is incomplete.")).toBeInTheDocument();
    expect(screen.queryByText("Unsaved — fix validation issues")).not.toBeInTheDocument();
  });
});
