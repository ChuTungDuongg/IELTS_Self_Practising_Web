import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { BuilderAutosaveStatus, BuilderLifecycleProvider, useBuilderAutosave } from "@/features/test-builder/builder-lifecycle";
import { ReadingBuilder } from "@/features/test-builder/reading-builder";
import { VersionActions } from "@/features/test-builder/version-actions";
import { createPassage, createQuestionGroup, updatePassage, type BuilderPassage, type BuilderQuestionGroup, type BuilderVersion } from "@/lib/api/builder";
import { validateVersion } from "@/lib/api/tests";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return { ...actual, createPassage: vi.fn(), createQuestionGroup: vi.fn(), updatePassage: vi.fn() };
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
