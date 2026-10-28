import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TestLibraryList } from "@/features/test-builder/test-library-list";
import { TeacherTestList } from "@/features/classrooms/teacher-test-list";
import { ApiError } from "@/lib/api/client";
import type { TestSummary } from "@/lib/api/schema";
import { cloneVersion, deleteTest, permanentlyDeleteTest, restoreTest } from "@/lib/api/tests";
import { renderWithLocale } from "./locale-test-utils";

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
  it("keeps search, authored content and open deletion focus while localizing chrome", () => {
    window.localStorage.clear();
    renderWithLocale(<TestLibraryList activeTests={[draftTest]} archivedTests={[]} />);
    const input = screen.getByPlaceholderText("Search tests…");
    fireEvent.change(input, { target: { value: "Fictional" } });
    fireEvent.click(screen.getByRole("button", { name: "Delete Fictional draft" }));
    const dialog = screen.getByRole("dialog");
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByPlaceholderText("Tìm đề…")).toBe(input);
    expect(input).toHaveValue("Fictional");
    expect(screen.getByRole("dialog", { name: "Xóa “Fictional draft”?" })).toBe(dialog);
    expect(cancel).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Fictional draft" })).toBeInTheDocument();
    expect(deleteTest).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the active test destructive action", () => {
    render(<TestLibraryList activeTests={[draftTest]} archivedTests={[]} />);

    expect(screen.getByRole("tab", { name: "Active (1)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByPlaceholderText("Search tests…")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search tests…").closest(".library-toolbar")).not.toHaveClass("surface-card");
    const row = screen.getByRole("heading", { name: "Fictional draft" }).closest("article")!;
    expect(row).toHaveClass("authoring-row");
    expect(within(row).getByText("Draft")).toBeInTheDocument();
    expect(row).not.toHaveTextContent(/1 Version|0 Published|v1/);
    expect(within(row).getByRole("link", { name: /Continue draft/ })).toHaveClass("btn-primary");
    expect(within(row).getByRole("button", { name: "Delete Fictional draft" })).toBeInTheDocument();
  });

  it("routes Edit on a published version to the draft returned by cloning", async () => {
    const published = { ...archivedTest, archived_at: null };
    const newDraftId = "55555555-5555-4555-8555-555555555555";
    vi.mocked(cloneVersion).mockResolvedValue({
      id: newDraftId,
      test_id: published.id,
      test_title: published.title,
      version_number: 2,
      status: "DRAFT",
      created_at: "2026-09-20T00:00:00Z",
      published_at: null,
      modules: [],
    });
    render(<TestLibraryList activeTests={[published]} archivedTests={[]} />);
    expect(screen.getByText("Published", { selector: ".authoring-status" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit test" }));

    await waitFor(() => expect(cloneVersion).toHaveBeenCalledWith(published.id, published.versions[0].id));
    expect(push).toHaveBeenCalledWith(`/admin/tests/${published.id}/versions/${newDraftId}/edit`);
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
    expect(refresh).not.toHaveBeenCalled();
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
  it("filters an overlapping published and draft test in either status and chooses the newest draft", () => {
    const oldDraft = { ...draftTest.versions[0], id: "old", version_number: 2 };
    const newDraft = { ...oldDraft, id: "new", version_number: 5 };
    const both = { ...draftTest, source_label: "Nguồn Mẫu", versions: [newDraft, archivedTest.versions[0], oldDraft] };
    render(<TestLibraryList activeTests={[both]} archivedTests={[]} />);
    const row = screen.getByRole("heading", { name: both.title }).closest("article")!;
    expect(within(row).getByText("Published")).toBeInTheDocument();
    expect(within(row).getByText("Unpublished changes")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Continue draft" })).toHaveAttribute("href", `/admin/tests/${both.id}/versions/new/edit`);
    fireEvent.change(screen.getByRole("combobox", { name: "Test status" }), { target: { value: "published" } });
    expect(screen.getByRole("heading", { name: both.title })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Test status" }), { target: { value: "draft" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search tests" }), { target: { value: "NGUỒN MẪU" } });
    expect(screen.getByRole("heading", { name: both.title })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Archived (0)" }));
    expect(screen.getByRole("textbox", { name: "Search tests" })).toHaveValue("NGUỒN MẪU");
    fireEvent.click(screen.getByRole("tab", { name: "Active (1)" }));
    expect(screen.getByRole("combobox", { name: "Test status" })).toHaveValue("draft");
    expect(cloneVersion).not.toHaveBeenCalled();
  });

  it("sorts titles and reports empty search results without fictional metadata", () => {
    const second = { ...draftTest, id: "second", title: "Alpha" };
    render(<TestLibraryList activeTests={[draftTest, second]} archivedTests={[]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Sort tests" }), { target: { value: "az" } });
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("Alpha");
    expect(document.body).not.toHaveTextContent(/quota|template|40 questions|100 tests/i);
    fireEvent.change(screen.getByRole("textbox", { name: "Search tests" }), { target: { value: "not found" } });
    expect(screen.getByText("No matching tests")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("keeps teacher content in its review workflow and hides permanent deletion", async () => {
    const owned = { ...archivedTest, archived_at: null, origin: "TEACHER" as const, owner_user_id: "teacher" };
    const foreign = { ...draftTest, id: "foreign", title: "Foreign", origin: "TEACHER" as const, owner_user_id: "other" };
    vi.mocked(cloneVersion).mockResolvedValue({ ...draftTest.versions[0], test_id: owned.id, test_title: owned.title, modules: [] });
    render(<TeacherTestList tests={[owned, foreign]} ownerId="teacher" archivedTests={[{ ...owned, archived_at: "2026-01-01" }]} />);
    expect(screen.queryByText("Foreign")).not.toBeInTheDocument();
    expect(screen.getByText(/administrator must review teacher content/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit test" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/teacher/tests/${owned.id}/versions/${draftTest.versions[0].id}/edit`));
    fireEvent.click(screen.getByRole("tab", { name: "Archived (1)" }));
    expect(screen.getByRole("button", { name: /Restore/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete permanently/ })).not.toBeInTheDocument();
  });

  it("does not present teacher-owned tests as admin-editable drafts", () => {
    const teacher = { ...draftTest, origin: "TEACHER" as const, owner_display_name: "A Teacher" };
    render(<TestLibraryList activeTests={[teacher]} archivedTests={[]} />);
    expect(screen.getByText("Teacher: A Teacher")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Continue draft" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Details" })).toHaveAttribute("href", `/admin/tests/${teacher.id}`);
  });

  it("shows loading failures rather than false empty-library counts", () => {
    render(<TestLibraryList activeTests={[]} archivedTests={[]} loadError />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the test library");
    expect(screen.queryByText("Active tests")).not.toBeInTheDocument();
  });

  it("confirms archival and moves a protected test to archived state", async () => {
    const published = { ...archivedTest, archived_at: null };
    vi.mocked(deleteTest).mockResolvedValue({ test_id: published.id, action: "ARCHIVED" });
    render(<TestLibraryList activeTests={[published]} archivedTests={[]} />);
    fireEvent.click(screen.getByRole("button", { name: `Archive ${published.title}` }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/archiv/i);
    fireEvent.click(within(dialog).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(deleteTest).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("tab", { name: "Archived (1)" }));
    expect(screen.getByRole("heading", { name: published.title })).toBeInTheDocument();
  });

  it("keeps restore failures visible and leaves protected tests archived", async () => {
    vi.mocked(restoreTest).mockRejectedValue(new ApiError("LOCKED", "Pending review locks this test.", 409));
    render(<TestLibraryList activeTests={[]} archivedTests={[archivedTest]} />);
    fireEvent.click(screen.getByRole("tab", { name: "Archived (1)" }));
    fireEvent.click(screen.getByRole("button", { name: `Restore ${archivedTest.title}` }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Pending review locks this test.");
    expect(screen.getByRole("heading", { name: archivedTest.title })).toBeInTheDocument();
  });

});
