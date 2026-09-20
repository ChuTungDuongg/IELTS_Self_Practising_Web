import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TestLibraryList } from "@/features/test-builder/test-library-list";
import { ApiError } from "@/lib/api/client";
import type { TestSummary } from "@/lib/api/schema";
import { deleteTest, permanentlyDeleteTest, restoreTest } from "@/lib/api/tests";

const refresh = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push }),
}));

vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return {
    ...actual,
    deleteTest: vi.fn(),
    restoreTest: vi.fn(),
    permanentlyDeleteTest: vi.fn(),
    cloneVersion: vi.fn(),
  };
});

const draftTest: TestSummary = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Fictional draft",
  description: null,
  source_label: null,
  test_number: null,
  archived_at: null,
  created_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
  versions: [
    {
      id: "22222222-2222-4222-8222-222222222222",
      version_number: 1,
      status: "DRAFT",
      created_at: "2026-09-19T00:00:00Z",
      published_at: null,
    },
  ],
};

const archivedTest: TestSummary = {
  ...draftTest,
  id: "33333333-3333-4333-8333-333333333333",
  title: "Fictional archived test",
  archived_at: "2026-09-19T01:00:00Z",
  versions: [
    {
      ...draftTest.versions[0],
      id: "44444444-4444-4444-8444-444444444444",
      status: "PUBLISHED",
      published_at: "2026-09-19T00:30:00Z",
    },
  ],
};

describe("TestLibraryList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the active test destructive action", () => {
    render(<TestLibraryList activeTests={[draftTest]} archivedTests={[]} />);

    expect(screen.getByRole("tab", { name: "Active (1)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByPlaceholderText("Search tests…")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Continue draft/ })).toHaveClass("btn-primary");
    expect(screen.getByRole("button", { name: "Delete Fictional draft" })).toHaveClass("btn-danger-ghost");
    expect(screen.getByRole("heading", { name: "Fictional draft" }).closest("article")).toHaveClass(
      "admin-test-card",
    );
  });

  it("cancels deletion without sending a request", () => {
    render(<TestLibraryList activeTests={[draftTest]} archivedTests={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(deleteTest).not.toHaveBeenCalled();
    expect(screen.getByText("Fictional draft")).toBeInTheDocument();
  });

  it("confirms deletion once and removes the test from active state", async () => {
    vi.mocked(deleteTest).mockResolvedValue({ test_id: draftTest.id, action: "DELETED" });
    render(<TestLibraryList activeTests={[draftTest]} archivedTests={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional draft" }));
    const confirm = screen.getByRole("button", { name: "Delete" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(deleteTest).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("Fictional draft")).not.toBeInTheDocument());
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("displays a structured backend deletion error", async () => {
    vi.mocked(deleteTest).mockRejectedValue(
      new ApiError("DELETE_CONFLICT", "The test could not be deleted.", 409),
    );
    render(<TestLibraryList activeTests={[draftTest]} archivedTests={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The test could not be deleted.");
    expect(screen.getByText("Fictional draft")).toBeInTheDocument();
  });

  it("lists archived tests and restores one to the active view", async () => {
    vi.mocked(restoreTest).mockResolvedValue({ ...archivedTest, archived_at: null });
    render(<TestLibraryList activeTests={[]} archivedTests={[archivedTest]} />);

    fireEvent.click(screen.getByRole("tab", { name: "Archived (1)" }));
    expect(screen.getByText("Fictional archived test")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore Fictional archived test" }));

    await waitFor(() => expect(restoreTest).toHaveBeenCalledWith(archivedTest.id));
    await waitFor(() => expect(screen.queryByText("Fictional archived test")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("tab", { name: "Active (1)" }));
    expect(screen.getByText("Fictional archived test")).toBeInTheDocument();
  });

  it("warns about attempt history before permanently deleting an archived test", async () => {
    vi.mocked(permanentlyDeleteTest).mockResolvedValue(undefined);
    render(<TestLibraryList activeTests={[]} archivedTests={[archivedTest]} />);
    fireEvent.click(screen.getByRole("tab", { name: "Archived (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently Fictional archived test" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("also delete all attempt history");
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(permanentlyDeleteTest).toHaveBeenCalledWith(archivedTest.id));
  });
});
