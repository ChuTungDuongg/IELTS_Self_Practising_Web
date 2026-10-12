import { fireEvent, render, screen, within } from "@testing-library/react";
import { renderWithLocale } from "./locale-test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LibraryPage from "@/app/library/page";
import TestVersionLibraryPage from "@/app/library/[versionId]/page";
import { getTest, getTests, getVersion } from "@/lib/api/tests";
import { versionDetailSchema, type TestSummary, type VersionDetail } from "@/lib/api/schema";

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
    { id: "33333333-3333-4333-8333-333333333333", module_type: "WRITING", title: null, recommended_duration_seconds: 3600, passage_count: 0, listening_part_count: 0, writing_task_count: 2, question_count: 0, writing_tasks: [{ id: "66666666-6666-4666-8666-666666666661", minimum_recommended_words: 150, recommended_duration_seconds: 1200, task_number: 1, task_type: "PIE_CHART", prompt_excerpt: "Describe fictional charts." }, { id: "66666666-6666-4666-8666-666666666662", minimum_recommended_words: 250, recommended_duration_seconds: 2400, task_number: 2, task_type: "OPINION", prompt_excerpt: "Discuss a fictional opinion." }] },
    { id: "44444444-4444-4444-8444-444444444444", module_type: "READING", title: null, recommended_duration_seconds: 3600, passage_count: 3, listening_part_count: 0, writing_task_count: 0, question_count: 40, reading_passages: [{ id: "77777777-7777-4777-8777-777777777777", title: "A fictional ship", order_index: 0, question_groups: [{ question_type: "matching", start_number: 5, end_number: 8, question_count: 4 }] }] },
    { id: "55555555-5555-4555-8555-555555555555", module_type: "LISTENING", title: null, recommended_duration_seconds: 1800, passage_count: 0, listening_part_count: 4, writing_task_count: 0, question_count: 40, listening_sections: [{ id: crypto.randomUUID(), title: "A fictional tour", order_index: 0, question_groups: [{ question_type: "note_completion", start_number: 1, end_number: 10, question_count: 10 }] }] },
  ],
};

const speakingModule: VersionDetail["modules"][number] = {
  id: "88888888-8888-4888-8888-888888888888", module_type: "SPEAKING", title: null,
  recommended_duration_seconds: 900, passage_count: 0, listening_part_count: 0,
  writing_task_count: 0, question_count: 5,
  speaking_parts: [
    { id: "99999999-9999-4999-8999-999999999992", part_number: 2, order_index: 1, title: "Individual Long Turn", prompts: [
      { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2", order_index: 1, prompt_type: "FOLLOW_UP", prompt_text: "Would you recommend this fictional garden?", cue_points: [] },
      { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1", order_index: 0, prompt_type: "LONG_TURN", prompt_text: "Describe a fictional garden beside a river.", cue_points: ["Where it is", "Why you like it"] },
    ] },
    { id: "99999999-9999-4999-8999-999999999991", part_number: 1, order_index: 0, title: "Introduction and Interview", prompts: [
      { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4", order_index: 1, prompt_type: "SHORT_ANSWER", prompt_text: "What do you enjoy about studying?", cue_points: [] },
      { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3", order_index: 0, prompt_type: "SHORT_ANSWER", prompt_text: "Are you working or studying?", cue_points: [] },
    ] },
    { id: "99999999-9999-4999-8999-999999999993", part_number: 3, order_index: 2, title: "Two-way Discussion", prompts: [
      { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5", order_index: 0, prompt_type: "SHORT_ANSWER", prompt_text: "Why are public gardens useful?", cue_points: [] },
    ] },
  ],
};

describe("Practice library", () => {
  it("summarizes Speaking by Part and discloses authored prompts only on request", async () => {
    const published = versionDetailSchema.parse({ ...detail, version_number: 13, modules: [...detail.modules, speakingModule] });
    vi.mocked(getVersion).mockResolvedValue(published);
    const view = renderWithLocale(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    const cards = [...view.container.querySelectorAll(".practice-skill-grid > article")];
    expect(cards).toHaveLength(4);
    expect(cards.map((card) => within(card as HTMLElement).getByRole("heading", { level: 2 }).textContent)).toEqual(["Reading", "Listening", "Writing", "Speaking"]);
    const speaking = cards[3] as HTMLElement;
    const metadata = within(speaking).getByText("Version").closest("dl")!;
    expect(metadata.textContent).toContain("Version13");
    expect(metadata.textContent).toContain("Questions5");
    expect(metadata.textContent).toContain("Parts3");
    expect(within(speaking).queryByText("No content added yet.")).not.toBeInTheDocument();
    expect(within(speaking).getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Speaking Part 1", "Speaking Part 2", "Speaking Part 3"]);
    expect(within(speaking).getByText("Individual Long Turn")).toBeInTheDocument();
    expect(within(speaking).getByText("Introduction and Interview")).toBeInTheDocument();
    const parts = [...speaking.querySelectorAll<HTMLDetailsElement>(".practice-speaking-disclosure")];
    expect(parts).toHaveLength(3);
    expect(parts.every((part) => !part.open)).toBe(true);
    expect(within(speaking).getAllByText("2 questions")).toHaveLength(2);
    expect(within(speaking).getByText("1 question")).toBeInTheDocument();
    expect([...speaking.querySelectorAll(".practice-speaking-part-summary > p:nth-child(2)")].map((item) => item.textContent)).toEqual(["Short answer", "Long turn · Follow-up", "Short answer"]);
    expect(within(speaking).getAllByText("View questions")).toHaveLength(3);
    expect(within(speaking).getByText("Are you working or studying?")).not.toBeVisible();
    fireEvent.click(within(parts[0]).getByText("View questions"));
    expect(parts[0].open).toBe(true);
    expect(within(parts[0]).getAllByText(/^Q[12]$/).map((item) => item.textContent)).toEqual(["Q1", "Q2"]);
    expect(within(parts[0]).getByText("Are you working or studying?")).toBeVisible();
    expect(within(parts[0]).getByText("What do you enjoy about studying?")).toBeVisible();
    fireEvent.click(within(parts[0]).getByText("View questions"));
    expect(parts[0].open).toBe(false);
    expect(within(parts[0]).getByText("Are you working or studying?")).not.toBeVisible();
    fireEvent.click(within(parts[1]).getByText("View questions"));
    expect(parts[1].open).toBe(true);
    expect([...parts[1].querySelectorAll(".practice-speaking-prompt-text")].map((item) => item.textContent)).toEqual(["Describe a fictional garden beside a river.", "Would you recommend this fictional garden?"]);
    expect(within(parts[1]).getByText("Long turn")).toBeInTheDocument();
    expect(within(parts[1]).getByText("Follow-up")).toBeInTheDocument();
    expect(within(parts[1]).getByText("Where it is")).toBeVisible();
    expect(within(parts[1]).getByText("Why you like it")).toBeVisible();
    fireEvent.click(within(parts[2]).getByText("View questions"));
    expect(within(parts[2]).getByText("Why are public gardens useful?")).toBeVisible();
    expect(within(cards[0] as HTMLElement).getByText("A fictional ship")).toBeInTheDocument();
    expect(within(cards[1] as HTMLElement).getByText("A fictional tour")).toBeInTheDocument();
    expect(within(cards[2] as HTMLElement).getByText("Describe fictional charts.")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(within(speaking).getByText("Phần Nói 1")).toBeInTheDocument();
    expect(within(speaking).getAllByText("Xem câu hỏi")).toHaveLength(3);
    expect(within(parts[1]).getByText("Trình bày dài")).toBeInTheDocument();
    expect(within(speaking).getByText("Câu hỏi")).toBeInTheDocument();
    expect(within(speaking).queryByText("speaking.summaryViewQuestions")).not.toBeInTheDocument();
  });
  it("enables durable Speaking starts and four-skill Full Mock readiness", async () => {
    vi.mocked(getVersion).mockResolvedValue({ ...detail, modules: [...detail.modules, { ...detail.modules[0], id: crypto.randomUUID(), module_type: "SPEAKING", recommended_duration_seconds: 900, writing_task_count: 0, writing_tasks: [] }] });
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    expect(screen.getAllByRole("button", { name: /Start/ }).map(button => button.textContent)).toEqual(["Start Full Mock", "Start READING", "Start LISTENING", "Start WRITING", "Start SPEAKING"]);
    expect(screen.getByRole("button", { name: "Start Full Mock" })).toBeEnabled();
  });
  it("translates the application fallback only when the authored description is null", async () => {
    window.localStorage.clear();
    vi.mocked(getTests).mockResolvedValue([{ ...publishedTest, description: null }]);
    renderWithLocale(await LibraryPage());
    const card = screen.getByRole("article");
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(within(card).getByText("Đề luyện IELTS đã xuất bản.")).toBeInTheDocument();
    expect(getTests).toHaveBeenCalledOnce(); expect(getVersion).toHaveBeenCalledOnce();
  });
  it("translates list and detail readiness while retaining authored data and server calls", async () => {
    window.localStorage.clear();
    const before = JSON.stringify({ publishedTest, detail });
    const list = renderWithLocale(await LibraryPage());
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("link", { name: "Mở đề" })).toHaveAttribute("href", `/library/${versionId}`);
    expect(screen.getByText(publishedTest.description!)).toBeInTheDocument();
    expect(getTests).toHaveBeenCalledOnce(); expect(getVersion).toHaveBeenCalledOnce();
    list.unmount(); window.localStorage.clear();
    vi.mocked(getVersion).mockResolvedValue({ ...detail, modules: detail.modules.filter((module) => module.module_type !== "READING") });
    renderWithLocale(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByText("Không thể làm bài thi thử: Thiếu mô-đun Đọc.")).toBeInTheDocument();
    expect(screen.getByText("Describe fictional charts.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: publishedTest.title })).toBeInTheDocument();
    expect(JSON.stringify({ publishedTest, detail })).toBe(before); expect(getTest).toHaveBeenCalledOnce();
  });
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

  it("requests public eligibility for the Library even when the viewer owns teacher content", async () => {
    render(await LibraryPage());
    expect(getTests).toHaveBeenCalledWith({ publicOnly: true }, expect.any(Function));
    expect(getVersion).toHaveBeenCalledWith(versionId, expect.any(Function), { publicOnly: true });
  });

  it("requires public eligibility on direct Library version links", async () => {
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    expect(getVersion).toHaveBeenCalledWith(versionId, expect.any(Function), { publicOnly: true });
  });

  it("shows available modules on the version detail route in canonical order", async () => {
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    const starts = screen.getAllByRole("button", { name: /Start/ });
    expect(starts.map((button) => button.textContent)).toEqual(["Start READING", "Start LISTENING", "Start WRITING"]);
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
      modules: [...detail.modules.map((module) => module.module_type === "READING"
        ? { ...module, recommended_duration_seconds: null }
        : module), { ...detail.modules[0], id: crypto.randomUUID(), module_type: "SPEAKING", recommended_duration_seconds: 900, writing_task_count: 0, writing_tasks: [] }],
    });
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    expect(screen.getByText("Full Mock unavailable: Reading recommended duration is missing.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start Full Mock" })).not.toBeInTheDocument();
  });
});
