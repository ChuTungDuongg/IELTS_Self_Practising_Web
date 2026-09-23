import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  BuilderLifecycleProvider,
  useBuilderAutosave,
  useBuilderLifecycle,
} from "@/features/test-builder/builder-lifecycle";
import { VersionActions } from "@/features/test-builder/version-actions";
import type { BuilderVersion } from "@/lib/api/builder";
import { deleteDraft, publishVersion, validateVersion } from "@/lib/api/tests";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, deleteDraft: vi.fn(), publishVersion: vi.fn(), validateVersion: vi.fn() };
});

const groupId = "33333333-3333-4333-8333-333333333333";

function builderVersion(status: "DRAFT" | "PUBLISHED" | "ARCHIVED"): BuilderVersion {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    test_id: "11111111-1111-4111-8111-111111111111",
    test_title: "Fictional test",
    version_number: 1,
    status,
    modules: [{
      id: "44444444-4444-4444-8444-444444444444",
      module_type: "READING",
      title: "Reading",
      recommended_duration_seconds: 3600,
      audio_asset: null,
      listening_parts: [],
      writing_tasks: [],
      passages: [{
        id: "55555555-5555-4555-8555-555555555555",
        title: "Urban foxes",
        order_index: 0,
        blocks: [],
        question_groups: [{
          id: groupId,
          question_type: "multiple_choice",
          instruction: "",
          config: {},
          order_index: 0,
          questions: [{
            id: "66666666-6666-4666-8666-666666666666",
            number: 1,
            prompt: "Question",
            config: {},
            answer_key: {},
            explanation: null,
            order_index: 0,
          }],
          image_asset_id: null,
          image_asset: null,
        }],
      }],
    }],
  };
}

function renderActions(status: "DRAFT" | "PUBLISHED" | "ARCHIVED") {
  return render(
    <BuilderLifecycleProvider>
      <VersionActions
        testId="11111111-1111-4111-8111-111111111111"
        version={builderVersion(status)}
      />
    </BuilderLifecycleProvider>,
  );
}

function PendingAutosave({ save }: { save: (value: string) => Promise<unknown> }) {
  const [value, setValue] = useState("initial");
  useBuilderAutosave({ resourceKey: "pending-fixture", value, save });
  return <button type="button" onClick={() => setValue("latest")}>Edit pending draft</button>;
}

function UnsavedCreateFixture() {
  const [value, setValue] = useState("initial");
  useBuilderAutosave({
    resourceKey: "new-resource",
    value,
    save: vi.fn(),
    enabled: false,
  });
  return <button type="button" onClick={() => setValue("edited")}>Edit new resource</button>;
}

function PendingMutation({ mutate }: { mutate: () => Promise<unknown> }) {
  const lifecycle = useBuilderLifecycle();
  return <button type="button" onClick={() => { void lifecycle.runMutation(mutate).catch(() => undefined); }}>Start mutation</button>;
}

function TransitionAwareInput() {
  const { transitioning } = useBuilderLifecycle();
  const [value, setValue] = useState("initial");
  return <input aria-label="Builder field" disabled={transitioning} value={value} onChange={(event) => setValue(event.target.value)} />;
}

function TransitionHarness({ ready }: { ready: () => void }) {
  const lifecycle = useBuilderLifecycle();
  return <button type="button" onClick={() => { void lifecycle.runTransition(async () => ready()); }}>Begin transition</button>;
}

describe("VersionActions draft deletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers Delete draft only for a draft version", () => {
    const { rerender } = renderActions("DRAFT");
    expect(screen.getByRole("button", { name: "Delete draft" })).toBeInTheDocument();

    rerender(
      <BuilderLifecycleProvider>
        <VersionActions
          testId="11111111-1111-4111-8111-111111111111"
          version={builderVersion("PUBLISHED")}
        />
      </BuilderLifecycleProvider>,
    );
    expect(screen.queryByRole("button", { name: "Delete draft" })).not.toBeInTheDocument();
  });

  it("shows IELTS readiness warnings separately from blocking errors", async () => {
    vi.mocked(validateVersion).mockResolvedValue({ valid: true, errors: [], warnings: [{ path: "listening.questions", message: "Listening contains 1 / 40 questions." }] });
    renderActions("DRAFT");
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("IELTS readiness")).toBeInTheDocument();
    expect(screen.getByText("Listening contains 1 / 40 questions.")).toBeInTheDocument();
    expect(screen.getByText("Validation complete.")).toBeInTheDocument();
    expect(screen.getByText("These recommendations do not block publishing.")).toBeInTheDocument();
  });

  it("publishes when validation is valid even when readiness warnings exist", async () => {
    vi.mocked(validateVersion).mockResolvedValue({ valid: true, errors: [], warnings: [{ path: "reading.questions", message: "Reading contains 1 / 40 questions." }] });
    vi.mocked(publishVersion).mockResolvedValue(undefined as never);
    renderActions("DRAFT");

    fireEvent.click(screen.getByRole("button", { name: "Publish version" }));

    await waitFor(() => expect(publishVersion).toHaveBeenCalledWith("22222222-2222-4222-8222-222222222222"));
    expect(screen.getByText("Reading contains 1 / 40 questions.")).toBeInTheDocument();
    expect(screen.getByText("These recommendations do not block publishing.")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it.each(["Validate", "Publish version"])("flushes pending changes before %s", async (actionLabel) => {
    let resolveSave!: () => void;
    const save = vi.fn(() => new Promise<void>((resolve) => { resolveSave = resolve; }));
    vi.mocked(validateVersion).mockResolvedValue({ valid: true, errors: [], warnings: [] });
    vi.mocked(publishVersion).mockResolvedValue(undefined as never);
    render(
      <BuilderLifecycleProvider>
        <PendingAutosave save={save} />
        <VersionActions testId="11111111-1111-4111-8111-111111111111" version={builderVersion("DRAFT")} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit pending draft" }));
    fireEvent.click(screen.getByRole("button", { name: actionLabel }));

    expect(save).toHaveBeenCalledWith("latest");
    expect(validateVersion).not.toHaveBeenCalled();
    expect(publishVersion).not.toHaveBeenCalled();
    resolveSave();

    await waitFor(() => expect(validateVersion).toHaveBeenCalledTimes(1));
    if (actionLabel === "Publish version") await waitFor(() => expect(publishVersion).toHaveBeenCalledTimes(1));
    else expect(publishVersion).not.toHaveBeenCalled();
  });

  it("waits for an already-running explicit mutation before validation", async () => {
    let resolveMutation!: () => void;
    const mutate = vi.fn(() => new Promise<void>((resolve) => { resolveMutation = resolve; }));
    vi.mocked(validateVersion).mockResolvedValue({ valid: true, errors: [], warnings: [] });
    render(
      <BuilderLifecycleProvider>
        <PendingMutation mutate={mutate} />
        <VersionActions testId="11111111-1111-4111-8111-111111111111" version={builderVersion("DRAFT")} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Start mutation" }));
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(validateVersion).not.toHaveBeenCalled();
    resolveMutation();
    await waitFor(() => expect(screen.getByRole("button", { name: "Validate" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(validateVersion).toHaveBeenCalledTimes(1));
  });

  it("re-flushes edits made while an explicit mutation is still running", async () => {
    let resolveMutation!: () => void;
    let resolveSave!: () => void;
    const mutate = vi.fn(() => new Promise<void>((resolve) => { resolveMutation = resolve; }));
    const save = vi.fn(() => new Promise<void>((resolve) => { resolveSave = resolve; }));
    const ready = vi.fn();
    render(
      <BuilderLifecycleProvider>
        <PendingAutosave save={save} />
        <PendingMutation mutate={mutate} />
        <TransitionHarness ready={ready} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Start mutation" }));
    fireEvent.click(screen.getByRole("button", { name: "Begin transition" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit pending draft" }));
    resolveMutation();

    await waitFor(() => expect(save).toHaveBeenCalledWith("latest"));
    expect(ready).not.toHaveBeenCalled();
    resolveSave();
    await waitFor(() => expect(ready).toHaveBeenCalledTimes(1));
  });

  it("blocks transitions that would discard an edited not-yet-created resource", async () => {
    render(
      <BuilderLifecycleProvider>
        <UnsavedCreateFixture />
        <VersionActions testId="11111111-1111-4111-8111-111111111111" version={builderVersion("DRAFT")} />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit new resource" }));
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(validateVersion).not.toHaveBeenCalled();
    expect(await screen.findByText("Fix invalid draft fields or retry the failed save before continuing.")).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("locks Builder editing until validation and publish both finish", async () => {
    let resolvePublish!: () => void;
    vi.mocked(validateVersion).mockResolvedValue({ valid: true, errors: [], warnings: [] });
    vi.mocked(publishVersion).mockImplementation(() => new Promise<void>((resolve) => { resolvePublish = resolve; }) as never);
    render(
      <BuilderLifecycleProvider>
        <TransitionAwareInput />
        <VersionActions testId="11111111-1111-4111-8111-111111111111" version={builderVersion("DRAFT")} />
      </BuilderLifecycleProvider>,
    );

    const field = screen.getByLabelText("Builder field");
    fireEvent.click(screen.getByRole("button", { name: "Publish version" }));
    await waitFor(() => expect(publishVersion).toHaveBeenCalledTimes(1));
    expect(field).toBeDisabled();

    resolvePublish();
    await waitFor(() => expect(field).toBeEnabled());
  });

  it("blocks publish and renders a complete contextual error outside the compact status", async () => {
    const message = "The answer key does not reference an available option, so this deliberately long validation explanation must remain fully readable.";
    vi.mocked(validateVersion).mockResolvedValue({
      valid: false,
      errors: [{ path: `reading.question_groups.${groupId}`, message }],
      warnings: [{ path: "reading.passages", message: "Reading contains 1 / 3 passages." }],
    });
    renderActions("DRAFT");

    fireEvent.click(screen.getByRole("button", { name: "Publish version" }));

    const panel = await screen.findByRole("alert");
    expect(within(panel).getByText("Cannot publish yet")).toBeInTheDocument();
    expect(within(panel).getByText("Reading Passage 1 · Urban foxes")).toBeInTheDocument();
    expect(within(panel).getByText("Multiple Choice — Single · Q1")).toBeInTheDocument();
    expect(within(panel).getByText(message)).toHaveClass("validation-issue-message");
    expect(within(panel).getByText(`reading.question_groups.${groupId}`)).toBeInTheDocument();
    expect(within(panel).getByText("IELTS readiness")).toBeInTheDocument();
    expect(publishVersion).not.toHaveBeenCalled();
    expect(within(screen.getByRole("status")).queryByText(message)).not.toBeInTheDocument();
  });

  it("cancels draft deletion without sending a request", () => {
    renderActions("DRAFT");
    fireEvent.click(screen.getByRole("button", { name: "Delete draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(deleteDraft).not.toHaveBeenCalled();
  });

  it("deletes once and navigates back to the Library", async () => {
    let resolveDelete: (() => void) | undefined;
    vi.mocked(deleteDraft).mockImplementation(
      () => new Promise<void>((resolve) => { resolveDelete = resolve; }),
    );
    renderActions("DRAFT");

    fireEvent.click(screen.getByRole("button", { name: "Delete draft" }));
    const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Delete draft" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(deleteDraft).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(confirm).toBeDisabled());
    resolveDelete?.();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/tests"));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("waits for an existing save and suppresses new mutations while deleting", async () => {
    let resolveSave: (() => void) | undefined;
    const save = vi.fn(() => new Promise<void>((resolve) => { resolveSave = resolve; }));
    const deletion = vi.fn().mockResolvedValue(undefined);

    function Harness() {
      const lifecycle = useBuilderLifecycle();
      return (
        <>
          <button disabled={lifecycle.deleting} onClick={() => void lifecycle.runMutation(save)}>
            Save
          </button>
          <button onClick={() => void lifecycle.beginDelete(deletion)}>Begin delete</button>
        </>
      );
    }

    render(
      <BuilderLifecycleProvider>
        <Harness />
      </BuilderLifecycleProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.click(screen.getByRole("button", { name: "Begin delete" }));

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(deletion).not.toHaveBeenCalled();

    resolveSave?.();
    await waitFor(() => expect(deletion).toHaveBeenCalledTimes(1));
  });

  it("serializes rapid builder mutations in submission order", async () => {
    let resolveFirst: (() => void) | undefined;
    const calls: string[] = [];
    const first = vi.fn(() => new Promise<void>((resolve) => {
      calls.push("first:start");
      resolveFirst = () => {
        calls.push("first:end");
        resolve();
      };
    }));
    const second = vi.fn(async () => {
      calls.push("second:start");
    });

    function Harness() {
      const lifecycle = useBuilderLifecycle();
      return (
        <>
          <button onClick={() => void lifecycle.runMutation(first)}>First save</button>
          <button onClick={() => void lifecycle.runMutation(second)}>Second save</button>
        </>
      );
    }

    render(<BuilderLifecycleProvider><Harness /></BuilderLifecycleProvider>);
    fireEvent.click(screen.getByRole("button", { name: "First save" }));
    fireEvent.click(screen.getByRole("button", { name: "Second save" }));

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
    resolveFirst?.();
    await waitFor(() => expect(second).toHaveBeenCalledTimes(1));
    expect(calls).toEqual(["first:start", "first:end", "second:start"]);
  });
});
