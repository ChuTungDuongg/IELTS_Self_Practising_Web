import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { BuilderAutosaveStatus, BuilderLifecycleProvider, useBuilderAutosave } from "@/features/test-builder/builder-lifecycle";
import { ReadingBuilder } from "@/features/test-builder/reading-builder";
import { VersionActions } from "@/features/test-builder/version-actions";
import { createPassage, createQuestionGroup, reorderQuestionGroups, updatePassage, updateQuestionGroup, type BuilderPassage, type BuilderQuestionGroup, type BuilderVersion } from "@/lib/api/builder";
import { validateVersion } from "@/lib/api/tests";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return { ...actual, createPassage: vi.fn(), createQuestionGroup: vi.fn(), reorderQuestionGroups: vi.fn(), updatePassage: vi.fn(), updateQuestionGroup: vi.fn() };
});
vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, validateVersion: vi.fn() };
});

function BlockingAutosave({ save }: { save: (value: string) => Promise<unknown> }) {
  const [value, setValue] = useState("initial");
  useBuilderAutosave({ resourceKey: "other-resource", value, save });
  return <button type="button" onClick={() => setValue("dirty")}>Dirty other resource</button>;
}

function group(number: number, prompt: string): BuilderQuestionGroup {
  const value = {
    ...questionRegistry.multiple_choice.createDefault(number),
    id: crypto.randomUUID(),
    revision: 1,
    order_index: number - 1,
    image_asset_id: null,
    image_asset: null,
  } as BuilderQuestionGroup;
  value.questions[0].prompt = prompt;
  return value;
}

function passage(orderIndex: number, title: string, groups: BuilderQuestionGroup[]): BuilderPassage {
  return {
    id: crypto.randomUUID(),
    revision: 1,
    title,
    order_index: orderIndex,
    blocks: [{ id: crypto.randomUUID(), type: "paragraph", label: "A", text: `${title} text` }],
    question_groups: groups,
  };
}

function version(passages: BuilderPassage[]): BuilderVersion {
  return {
    id: crypto.randomUUID(),
    test_id: crypto.randomUUID(),
    test_title: "Reading practice",
    version_number: 1,
    status: "DRAFT",
    modules: [{
      id: crypto.randomUUID(),
      revision: 1,
      module_type: "READING",
      title: "Reading",
      recommended_duration_seconds: 3600,
      audio_asset: null,
      passages,
      listening_parts: [],
      writing_tasks: [],
    }],
  };
}

describe("Reading Builder editor identity", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.useRealTimers());

  it("uses each acknowledged passage revision for the next autosave", async () => {
    vi.useFakeTimers();
    const initial = passage(0, "First passage", []);
    vi.mocked(updatePassage)
      .mockResolvedValueOnce({ ...initial, title: "First edit", revision: 2 })
      .mockResolvedValueOnce({ ...initial, title: "Second edit", revision: 3 });
    render(<BuilderLifecycleProvider><ReadingBuilder version={version([initial])} /><BuilderAutosaveStatus /></BuilderLifecycleProvider>);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit passage" })); await Promise.resolve(); });
    fireEvent.change(screen.getByLabelText("Passage title"), { target: { value: "First edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(updatePassage).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Saved")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Passage title"), { target: { value: "Second edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(updatePassage).toHaveBeenCalledTimes(2);
    expect(vi.mocked(updatePassage).mock.calls.map(([, body]) => body.expected_revision)).toEqual([1, 2]);
  });

  it("shows the saved passage response in both editor and summary without a reload", async () => {
    vi.useFakeTimers();
    const initial = passage(0, "Original passage", []);
    const builderVersion = version([initial]);
    vi.mocked(updatePassage).mockResolvedValue({ ...initial, revision: 2, title: "Server passage" });
    const { rerender } = render(<BuilderLifecycleProvider><ReadingBuilder version={builderVersion} /><BuilderAutosaveStatus /></BuilderLifecycleProvider>);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit passage" })); await Promise.resolve(); });
    fireEvent.change(screen.getByLabelText("Passage title"), { target: { value: "Client passage" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByLabelText("Passage title")).toHaveValue("Server passage");
    expect(screen.getAllByText("Server passage").length).toBeGreaterThan(0);
    expect(screen.getByText("Saved")).toBeInTheDocument();
    rerender(<BuilderLifecycleProvider><ReadingBuilder version={{ ...builderVersion }} /><BuilderAutosaveStatus /></BuilderLifecycleProvider>);
    expect(screen.getByLabelText("Passage title")).toHaveValue("Server passage");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Close" })); await Promise.resolve(); });
    expect(screen.getByRole("heading", { name: "Server passage" })).toBeInTheDocument();
  });

  it("shows the saved group response in its editor and card without a reload", async () => {
    vi.useFakeTimers();
    const initial = group(13, "Original prompt");
    initial.instruction = "Original instruction";
    vi.mocked(updateQuestionGroup).mockResolvedValue({
      ...initial,
      revision: 2,
      instruction: "Server instruction",
      questions: initial.questions.map((question) => ({ ...question, prompt: "Server prompt" })),
    });
    render(<BuilderLifecycleProvider><ReadingBuilder version={version([passage(0, "Passage", [initial])])} /><BuilderAutosaveStatus /></BuilderLifecycleProvider>);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit / Preview" })); await Promise.resolve(); });
    fireEvent.change(screen.getByLabelText("Group instruction"), { target: { value: "Client instruction" } });
    await act(async () => { fireEvent.click(screen.getAllByRole("button", { name: "Save now" })[0]); await Promise.resolve(); });
    expect(screen.getByLabelText("Group instruction")).toHaveValue("Server instruction");
    expect(screen.getByLabelText("Prompt")).toHaveValue("Server prompt");
    expect(screen.getByText(/Server instruction/)).toBeInTheDocument();
    expect(screen.getByText("Saved")).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Close" })); await Promise.resolve(); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit / Preview" })); await Promise.resolve(); });
    expect(screen.getByLabelText("Prompt")).toHaveValue("Server prompt");
  });

  it("uses the returned module order immediately after moving a group", async () => {
    const first = group(1, "First prompt");
    const second = group(2, "Second prompt");
    const originalPassage = passage(0, "Passage", [first, second]);
    const builderVersion = version([originalPassage]);
    const readingModule = builderVersion.modules[0];
    vi.mocked(updatePassage).mockResolvedValue({ ...originalPassage, revision: 2, title: "Saved passage" });
    vi.mocked(reorderQuestionGroups).mockResolvedValue({
      ...readingModule,
      revision: 2,
      passages: [{
        ...readingModule.passages[0],
        question_groups: [{ ...second, order_index: 0 }, { ...first, order_index: 1 }],
      }],
    });
    render(<BuilderLifecycleProvider><ReadingBuilder version={builderVersion} /></BuilderLifecycleProvider>);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit passage" })); await Promise.resolve(); });
    fireEvent.change(screen.getByLabelText("Passage title"), { target: { value: "Client passage" } });
    fireEvent.click(screen.getByRole("button", { name: "Save now" }));
    await waitFor(() => expect(screen.getByLabelText("Passage title")).toHaveValue("Saved passage"));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Close" })); await Promise.resolve(); });
    fireEvent.click(screen.getAllByRole("button", { name: "Move question group down" })[0]);
    await waitFor(() => expect(reorderQuestionGroups).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getAllByText(/^Q[12]$/).map((element) => element.textContent)).toEqual(["Q2", "Q1"]));
  });

  it("switches persisted passage editors without carrying local state", async () => {
    render(
      <BuilderLifecycleProvider>
        <ReadingBuilder version={version([passage(0, "First passage", []), passage(1, "Second passage", [])])} />
      </BuilderLifecycleProvider>,
    );

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit passage" })[0]);
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Passage title")).toHaveValue("First passage");

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit passage" })[1]);
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Passage title")).toHaveValue("Second passage");
  });

  it("switches persisted group editors without carrying local state", async () => {
    const groups = [group(1, "First group prompt"), group(2, "Second group prompt")];
    render(
      <BuilderLifecycleProvider>
        <ReadingBuilder version={version([passage(0, "Passage", groups)])} />
      </BuilderLifecycleProvider>,
    );

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit / Preview" })[0]);
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Prompt")).toHaveValue("First group prompt");

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit / Preview" })[1]);
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Prompt")).toHaveValue("Second group prompt");
  });

  it("opens an imported Reading completion group at its persisted number after a gap", async () => {
    const first = group(1, "First prompt");
    const later = {
      ...questionRegistry.summary_completion.createDefault(14),
      id: crypto.randomUUID(),
      revision: 1,
      order_index: 1,
      image_asset_id: null,
      image_asset: null,
    } as BuilderQuestionGroup;
    render(<BuilderLifecycleProvider><ReadingBuilder version={version([passage(0, "Passage", [first, later])])} /></BuilderLifecycleProvider>);

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit / Preview" })[1]);
      await Promise.resolve();
    });
    expect(screen.getByRole("group", { name: "Question 14 answer editor" })).toBeInTheDocument();
  });

  it("creates an edited new passage without its own draft blocking the POST", async () => {
    let resolveOtherSave!: () => void;
    const saveOther = vi.fn(() => new Promise<void>((resolve) => { resolveOtherSave = resolve; }));
    vi.mocked(createPassage).mockResolvedValue(undefined as never);
    render(
      <BuilderLifecycleProvider>
        <BlockingAutosave save={saveOther} />
        <ReadingBuilder version={version([])} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add passage" }));
    const title = await screen.findByLabelText("Passage title");
    fireEvent.change(title, { target: { value: "Edited new passage" } });
    fireEvent.click(screen.getByRole("button", { name: "Dirty other resource" }));
    fireEvent.click(screen.getByRole("button", { name: "Create passage" }));
    expect(title).toBeDisabled();
    fireEvent.change(title, { target: { value: "Late edit that must not race the captured POST" } });
    expect(saveOther).toHaveBeenCalledWith("dirty");
    expect(createPassage).not.toHaveBeenCalled();
    resolveOtherSave();

    await waitFor(() => expect(createPassage).toHaveBeenCalledTimes(1));
    expect(createPassage).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ title: "Edited new passage" }),
    );
  });

  it("creates an edited new question group without its own draft blocking the POST", async () => {
    let resolveOtherSave!: () => void;
    const saveOther = vi.fn(() => new Promise<void>((resolve) => { resolveOtherSave = resolve; }));
    vi.mocked(createQuestionGroup).mockResolvedValue(undefined as never);
    const existingPassage = passage(0, "Passage", []);
    render(
      <BuilderLifecycleProvider>
        <BlockingAutosave save={saveOther} />
        <ReadingBuilder version={version([existingPassage])} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add question group" }));
    const prompt = await screen.findByLabelText("Prompt");
    fireEvent.change(prompt, { target: { value: "Edited new group" } });
    fireEvent.click(screen.getByRole("button", { name: "Dirty other resource" }));
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    expect(prompt).toBeDisabled();
    fireEvent.change(prompt, { target: { value: "Late edit that must not race the captured POST" } });
    expect(saveOther).toHaveBeenCalledWith("dirty");
    expect(createQuestionGroup).not.toHaveBeenCalled();
    resolveOtherSave();

    await waitFor(() => expect(createQuestionGroup).toHaveBeenCalledTimes(1));
    expect(createQuestionGroup).toHaveBeenCalledWith(
      existingPassage.id,
      expect.objectContaining({ questions: [expect.objectContaining({ prompt: "Edited new group" })] }),
    );
  });

  it("waits for a just-submitted create before validating the version", async () => {
    let resolveCreate!: () => void;
    vi.mocked(createQuestionGroup).mockImplementation(() => new Promise((resolve) => {
      resolveCreate = () => resolve(undefined as never);
    }));
    vi.mocked(validateVersion).mockResolvedValue({ valid: true, errors: [], warnings: [] });
    const builderVersion = version([passage(0, "Passage", [])]);
    render(
      <BuilderLifecycleProvider>
        <VersionActions testId={builderVersion.test_id} version={builderVersion} />
        <ReadingBuilder version={builderVersion} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add question group" }));
    fireEvent.change(await screen.findByLabelText("Prompt"), { target: { value: "Ready to create" } });
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(createQuestionGroup).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();

    expect(validateVersion).not.toHaveBeenCalled();
    resolveCreate();
    await waitFor(() => expect(screen.getByRole("button", { name: "Validate" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(validateVersion).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Validation complete.")).toBeInTheDocument();
  });
});
