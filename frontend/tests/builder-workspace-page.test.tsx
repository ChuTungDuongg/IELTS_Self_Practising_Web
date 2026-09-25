import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VersionEditorPage from "@/app/admin/tests/[testId]/versions/[versionId]/edit/page";
import { getBuilderVersion } from "@/lib/api/builder";
import { ApiError } from "@/lib/api/client";
import { getTest, updateTest } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";

const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => { throw new Error("NEXT_NOT_FOUND"); }),
  redirect: vi.fn((path: string) => { throw new Error(`NEXT_REDIRECT:${path}`); }),
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({ ...navigation, useRouter: () => ({ refresh: navigation.refresh, push: vi.fn() }) }));
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return { ...actual, getBuilderVersion: vi.fn() };
});
vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, getTest: vi.fn(), updateTest: vi.fn() };
});

const testId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";

describe("Builder workspace page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("opens the real Listening workspace without a module or audio", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: testId, test_title: "Practice", version_number: 1, status: "DRAFT", modules: [] });

    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }), searchParams: Promise.resolve({ workspace: "listening" }) }));

    expect(screen.getByRole("heading", { name: "Build the Listening module" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Build the Reading module" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Listening/ })).toHaveAttribute("aria-current", "page");
  });

  it("edits draft test details from persisted values and refreshes", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: testId, test_title: "Test 2", test_description: "Original summary", version_number: 1, status: "DRAFT", modules: [] });
    vi.mocked(updateTest).mockResolvedValue({ id: testId, title: "Cambridge 11 Test 2", description: "Updated summary", source_label: null, test_number: null, archived_at: null, created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z", versions: [] });
    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }) }));

    fireEvent.click(screen.getByRole("button", { name: "Edit test details" }));
    const input = screen.getByRole("textbox", { name: "Test name" });
    expect(input).toHaveValue("Test 2");
    expect(screen.getByRole("textbox", { name: "Description" })).toHaveValue("Original summary");
    fireEvent.change(input, { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "  Cambridge 11 Test 2  " } });
    fireEvent.change(screen.getByRole("textbox", { name: "Description" }), { target: { value: "  Updated summary  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(updateTest).toHaveBeenCalledWith(testId, { title: "Cambridge 11 Test 2", description: "Updated summary" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Cambridge 11 Test 2" })).toBeInTheDocument());
    expect(screen.getByText("Updated summary")).toBeInTheDocument();
    expect(navigation.refresh).toHaveBeenCalledOnce();
  });

  it("cancels without a request and displays API errors", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: testId, test_title: "Test 2", version_number: 1, status: "DRAFT", modules: [] });
    vi.mocked(updateTest).mockRejectedValue(new Error("Rename failed"));
    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }) }));
    fireEvent.click(screen.getByRole("button", { name: "Edit test details" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(updateTest).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Test 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit test details" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Test name" }), { target: { value: "New title" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Rename failed");
    expect(screen.getByRole("heading", { name: "Test 2" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Test name" })).toHaveValue("New title");
  });

  it("does not expose rename on a published Builder", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: testId, test_title: "Published test", version_number: 1, status: "PUBLISHED", modules: [] });
    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }) }));
    expect(screen.queryByRole("button", { name: "Edit test details" })).not.toBeInTheDocument();
  });

  it("shows passage, section, question-type, and Writing tags in the overview", async () => {
    const question = { id: crypto.randomUUID(), number: 1, prompt: "Fictional prompt", config: {}, answer_key: {}, explanation: null, order_index: 0 };
    const group = { id: crypto.randomUUID(), revision: 1, question_type: "matching" as const, instruction: "", config: {}, order_index: 0, questions: [question], image_asset_id: null, image_asset: null };
    vi.mocked(getBuilderVersion).mockResolvedValue({
      id: versionId, test_id: testId, test_title: "Fictional test", version_number: 1, status: "DRAFT",
      modules: [
        { id: crypto.randomUUID(), revision: 1, module_type: "READING", title: "Reading", recommended_duration_seconds: 3600, audio_asset: null, passages: [{ id: crypto.randomUUID(), revision: 1, title: "A fictional ship", order_index: 0, blocks: [], question_groups: [group, { ...group, id: crypto.randomUUID(), order_index: 1 }] }], listening_parts: [], writing_tasks: [] },
        { id: crypto.randomUUID(), revision: 1, module_type: "LISTENING", title: "Listening", recommended_duration_seconds: 1800, audio_asset: null, passages: [], listening_parts: [{ id: crypto.randomUUID(), revision: 1, title: "A fictional tour", order_index: 0, question_groups: [{ ...group, id: crypto.randomUUID(), question_type: "note_completion" }] }], writing_tasks: [] },
        { id: crypto.randomUUID(), revision: 1, module_type: "WRITING", title: "Writing", recommended_duration_seconds: 3600, audio_asset: null, passages: [], listening_parts: [], writing_tasks: [{ id: crypto.randomUUID(), revision: 1, task_number: 1, task_type: "PIE_CHART", prompt: "Describe fictional data.", image_asset_id: null, image_asset: null, minimum_recommended_words: 150, recommended_duration_seconds: 1200, order_index: 0 }] },
      ],
    });
    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }) }));
    expect(screen.getAllByText(/Recommended time: 60 min/)).toHaveLength(2);
    expect(screen.getByText(/Recommended time: 30 min/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Edit duration" })).toHaveLength(3);
    expect(screen.getByText("A fictional ship")).toBeInTheDocument();
    expect(screen.getAllByText("Matching")).toHaveLength(1);
    expect(screen.getByText("A fictional tour")).toBeInTheDocument();
    expect(screen.getByText("Note Completion")).toBeInTheDocument();
    expect(screen.getByText("Pie chart")).toBeInTheDocument();
  });

  it("opens the Writing workspace without a module", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: testId, test_title: "Practice", version_number: 1, status: "DRAFT", modules: [] });

    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }), searchParams: Promise.resolve({ workspace: "writing" }) }));

    expect(screen.getByRole("heading", { name: "Build the Writing module" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Writing/ })).toHaveAttribute("aria-current", "page");
  });

  it("rejects a real version paired with the wrong test", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: crypto.randomUUID(), test_title: "Practice", version_number: 1, status: "DRAFT", modules: [] });
    await expect(VersionEditorPage({ params: Promise.resolve({ testId, versionId }) })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.notFound).toHaveBeenCalledOnce();
  });

  it("recovers a stale version URL by redirecting to the current draft", async () => {
    const currentDraftId = "33333333-3333-4333-8333-333333333333";
    vi.mocked(getBuilderVersion).mockRejectedValue(new ApiError("TEST_VERSION_NOT_FOUND", "Missing", 404));
    vi.mocked(getTest).mockResolvedValue({
      id: testId,
      title: "Practice",
      description: null,
      source_label: null,
      test_number: null,
      archived_at: null,
      created_at: "2026-09-20T00:00:00Z",
      updated_at: "2026-09-20T00:00:00Z",
      versions: [{ id: currentDraftId, version_number: 2, status: "DRAFT", created_at: "2026-09-20T00:00:00Z", published_at: null }],
    });

    await expect(VersionEditorPage({ params: Promise.resolve({ testId, versionId }) })).rejects.toThrow(`NEXT_REDIRECT:${builderEditPath(testId, currentDraftId)}`);
    expect(navigation.redirect).toHaveBeenCalledWith(builderEditPath(testId, currentDraftId));
    expect(navigation.notFound).not.toHaveBeenCalled();
  });
});
