import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import VersionEditorPage from "@/app/admin/tests/[testId]/versions/[versionId]/edit/page";
import { getBuilderVersion } from "@/lib/api/builder";

vi.mock("next/navigation", () => ({ notFound: vi.fn(), useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return { ...actual, getBuilderVersion: vi.fn() };
});

const testId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";

describe("Builder workspace page", () => {
  it("opens the real Listening workspace without a module or audio", async () => {
    vi.mocked(getBuilderVersion).mockResolvedValue({ id: versionId, test_id: testId, test_title: "Practice", version_number: 1, status: "DRAFT", modules: [] });

    render(await VersionEditorPage({ params: Promise.resolve({ testId, versionId }), searchParams: Promise.resolve({ workspace: "listening" }) }));

    expect(screen.getByRole("heading", { name: "Build the Listening module" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Build the Reading module" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Listening/ })).toHaveAttribute("aria-current", "page");
  });
});
