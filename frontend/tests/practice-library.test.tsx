import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LibraryPage from "@/app/library/page";
import TestVersionLibraryPage from "@/app/library/[versionId]/page";
import { getTest, getTests, getVersion } from "@/lib/api/tests";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";

vi.mock("next/navigation", () => ({ notFound: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/tests", () => ({ getTests: vi.fn(), getTest: vi.fn(), getVersion: vi.fn() }));
vi.mock("@/features/exam/start-attempt", () => ({
  StartAttempt: ({ module }: { module: string }) => <button>Start {module}</button>,
}));

const testId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";
const publishedTest: TestSummary = {
  id: testId, title: "Fictional complete test", description: "Three focused skill modules.",
  source_label: null, test_number: 1, archived_at: null,
  created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
  versions: [{ id: versionId, version_number: 2, status: "PUBLISHED", created_at: "2026-09-20T00:00:00Z", published_at: "2026-09-20T00:00:00Z" }],
};
const detail: VersionDetail = {
  ...publishedTest.versions[0], test_id: testId, test_title: publishedTest.title,
  modules: [
    { id: "33333333-3333-4333-8333-333333333333", module_type: "WRITING", title: null, recommended_duration_seconds: 3600, passage_count: 0, listening_part_count: 0, writing_task_count: 2, question_count: 0, writing_tasks: [{ task_number: 1, task_type: "PIE_CHART", prompt_excerpt: "Describe fictional charts." }, { task_number: 2, task_type: "OPINION", prompt_excerpt: "Discuss a fictional opinion." }] },
    { id: "44444444-4444-4444-8444-444444444444", module_type: "READING", title: null, recommended_duration_seconds: 3600, passage_count: 3, listening_part_count: 0, writing_task_count: 0, question_count: 40, reading_passages: [{ title: "A fictional ship", order_index: 0, question_groups: [{ question_type: "matching", start_number: 5, end_number: 8 }] }] },
    { id: "55555555-5555-4555-8555-555555555555", module_type: "LISTENING", title: null, recommended_duration_seconds: 1800, passage_count: 0, listening_part_count: 4, writing_task_count: 0, question_count: 40, listening_sections: [{ title: "A fictional tour", order_index: 0, question_groups: [{ question_type: "note_completion", start_number: 1, end_number: 10 }] }] },
  ],
};

describe("Practice library", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getTests).mockResolvedValue([publishedTest]);
    vi.mocked(getTest).mockResolvedValue(publishedTest);
    vi.mocked(getVersion).mockResolvedValue(detail);
  });

  it("shows one landing card per published test version", async () => {
    render(await LibraryPage());
    const card = screen.getByRole("heading", { name: publishedTest.title }).closest("article")!;
    expect(within(card).getByText("3 skills available")).toBeInTheDocument();
    expect(within(card).getByText("Reading")).toBeInTheDocument();
    expect(within(card).getByText("Listening")).toBeInTheDocument();
    expect(within(card).getByText("Writing")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Open test/ })).toHaveAttribute("href", `/library/${versionId}`);
    expect(screen.queryByRole("button", { name: /Start/ })).not.toBeInTheDocument();
  });

  it("shows available modules on the version detail route in canonical order", async () => {
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    const starts = screen.getAllByRole("button", { name: /Start/ });
    expect(starts.map((button) => button.textContent)).toEqual(["Start Full Mock", "Start READING", "Start LISTENING", "Start WRITING"]);
    expect(screen.getByText("Reading practice")).toHaveClass("practice-module-kicker");
    expect(screen.getByText("Writing practice")).toHaveClass("practice-module-kicker");
    expect(screen.queryByText("SPEAKING")).not.toBeInTheDocument();
    expect(screen.getByText("A fictional ship")).toBeInTheDocument();
    expect(screen.getByText("Matching")).toBeInTheDocument();
    expect(screen.getByText("A fictional tour")).toBeInTheDocument();
    expect(screen.getByText("Note Completion")).toBeInTheDocument();
    expect(screen.getByText("Pie chart")).toBeInTheDocument();
    expect(screen.getByText("Opinion / Agree or disagree")).toBeInTheDocument();
  });

  it("keeps Full Mock unavailable when a published module has no duration", async () => {
    vi.mocked(getVersion).mockResolvedValue({
      ...detail,
      modules: detail.modules.map((module) => module.module_type === "READING"
        ? { ...module, recommended_duration_seconds: null }
        : module),
    });
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    expect(screen.getByText("Full Mock unavailable: Reading recommended duration is missing.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start Full Mock" })).not.toBeInTheDocument();
  });
});
