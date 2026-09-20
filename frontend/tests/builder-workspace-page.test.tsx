import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VersionEditorPage from "@/app/admin/tests/[testId]/versions/[versionId]/edit/page";
import { getBuilderVersion } from "@/lib/api/builder";
import { ApiError } from "@/lib/api/client";
import { getTest } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";

const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => { throw new Error("NEXT_NOT_FOUND"); }),
  redirect: vi.fn((path: string) => { throw new Error(`NEXT_REDIRECT:${path}`); }),
}));
vi.mock("next/navigation", () => ({ ...navigation, useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return { ...actual, getBuilderVersion: vi.fn() };
});
vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, getTest: vi.fn() };
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
