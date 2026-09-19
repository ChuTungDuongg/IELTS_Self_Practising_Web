import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  BuilderLifecycleProvider,
  useBuilderLifecycle,
} from "@/features/test-builder/builder-lifecycle";
import { VersionActions } from "@/features/test-builder/version-actions";
import { deleteDraft, validateVersion } from "@/lib/api/tests";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, deleteDraft: vi.fn(), validateVersion: vi.fn() };
});

function renderActions(status: "DRAFT" | "PUBLISHED" | "ARCHIVED") {
  return render(
    <BuilderLifecycleProvider>
      <VersionActions
        testId="11111111-1111-4111-8111-111111111111"
        versionId="22222222-2222-4222-8222-222222222222"
        status={status}
      />
    </BuilderLifecycleProvider>,
  );
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
          versionId="22222222-2222-4222-8222-222222222222"
          status="PUBLISHED"
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
    expect(screen.getByText("Version is valid.")).toBeInTheDocument();
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
});
