import { fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { renderWithLocale } from "./locale-test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LibraryPage from "@/app/library/page";
import { LibraryContent } from "@/features/practice/library-content";
import TestVersionLibraryPage from "@/app/library/[versionId]/page";
import { getTest, getTests, getVersion } from "@/lib/api/tests";
import { notFound } from "next/navigation";
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
  it.each([false, true])("loads six catalog cards with batched summaries=%s", async (embedded) => {
    const records = Array.from({ length: 6 }, () => {
      const testId = crypto.randomUUID(), versionId = crypto.randomUUID();
      const version = { ...detail, id: versionId, test_id: testId };
      return { ...publishedTest, id: testId, versions: [version], ...(embedded ? { published_detail: version } : {}) };
    });
    vi.mocked(getTests).mockResolvedValue(records);
    vi.mocked(getVersion).mockImplementation(async id => { const test = records.find(record => record.versions[0].id === id)!; return { ...detail, id, test_id: test.id }; });
    render(await LibraryPage());
    expect(screen.getAllByRole("article")).toHaveLength(6);
    expect(getTests).toHaveBeenCalledOnce();
    expect(getVersion).toHaveBeenCalledTimes(embedded ? 0 : 6);
  });
  it("summarizes Speaking by Part and discloses authored prompts only on request", async () => {
    const published = versionDetailSchema.parse({ ...detail, version_number: 13, modules: [...detail.modules, speakingModule] });
    vi.mocked(getVersion).mockResolvedValue(published);
    const view = renderWithLocale(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    const cards = [...view.container.querySelectorAll(".practice-skill-grid > article")];
    expect(cards).toHaveLength(4);
    expect(cards.map((card) => within(card as HTMLElement).getByRole("heading", { level: 2 }).textContent)).toEqual(["Reading", "Listening", "Writing", "Speaking"]);
    const speaking = cards[3] as HTMLElement;
    const metadata = speaking.querySelector("dl")!;
    expect(metadata.textContent).not.toContain("Version13");
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
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(getTests).mockResolvedValue([publishedTest]);
    vi.mocked(getTest).mockResolvedValue(publishedTest);
    vi.mocked(getVersion).mockResolvedValue(detail);
  });

  it("shows one landing card per published test version", async () => {
    render(await LibraryPage());
    const card = screen.getByRole("heading", { name: publishedTest.title }).closest("article")!;
    expect(within(card).queryByText("Complete test", { exact: true })).not.toBeInTheDocument();
    expect(within(card).getByText("Official")).toBeInTheDocument(); expect(within(card).queryByText("Version 2")).not.toBeInTheDocument();
    expect(within(card).getByText("Published")).toBeInTheDocument();
    expect(within(card).getByText("3 skills available")).toBeInTheDocument();
    expect(within(card).getByText("Reading")).toBeInTheDocument();
    expect(within(card).getByText("Listening")).toBeInTheDocument();
    expect(within(card).getByText("Writing")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Open test/ })).toHaveAttribute("href", `/library/${versionId}`);
    expect(screen.queryByRole("button", { name: /Start/ })).not.toBeInTheDocument();
  });

  it("requests public eligibility for the Library even when the viewer owns teacher content", async () => {
    render(await LibraryPage());
    expect(getTests).toHaveBeenCalledWith({ publicOnly: true, includeDetails: true }, expect.any(Function));
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
  it("combines case-insensitive source search and multi-skill filtering without refetching", async () => {
    const writingOnly = { ...detail, id: crypto.randomUUID(), test_id: crypto.randomUUID(), modules: [detail.modules[0]] };
    const tests = [
      { ...publishedTest, source_label: "Nguồn Mẫu", published_detail: detail },
      { ...publishedTest, id: writingOnly.test_id, title: "Another test", source_label: null, versions: [writingOnly], published_detail: writingOnly },
    ];
    vi.mocked(getTests).mockResolvedValue(tests);
    renderWithLocale(await LibraryPage());
    const group = screen.getByRole("group", { name: "Filter tests by skill" });
    fireEvent.click(within(group).getByRole("button", { name: "Writing" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
    fireEvent.change(screen.getByRole("textbox", { name: "Search the test library" }), { target: { value: "NGUỒN MẪU" } });
    expect(screen.getAllByRole("article")).toHaveLength(1);
    fireEvent.click(within(group).getByRole("button", { name: "Reading" }));
    expect(screen.getByRole("heading", { name: publishedTest.title })).toBeInTheDocument();
    fireEvent.click(within(group).getByRole("button", { name: "Speaking" }));
    expect(screen.getByRole("heading", { name: "No matching tests" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByRole("textbox", { name: "Search the test library" })).toHaveValue("");
    expect(getTests).toHaveBeenCalledOnce(); expect(getVersion).not.toHaveBeenCalled();
  });

  it("sorts by real update dates and title and keeps the selected filter", async () => {
    const otherDetail = { ...detail, id: crypto.randomUUID(), test_id: crypto.randomUUID() };
    vi.mocked(getTests).mockResolvedValue([
      { ...publishedTest, title: "Zulu", updated_at: "2026-01-01T00:00:00Z", published_detail: detail },
      { ...publishedTest, id: otherDetail.test_id, title: "Alpha", updated_at: "2026-10-01T00:00:00Z", versions: [otherDetail], published_detail: otherDetail },
    ]);
    render(await LibraryPage());
    const group = screen.getByRole("group", { name: "Filter tests by skill" });
    fireEvent.click(within(group).getByRole("button", { name: "Reading" }));
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("Alpha");
    fireEvent.change(screen.getByRole("combobox", { name: "Sort tests" }), { target: { value: "oldest" } });
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("Zulu");
    fireEvent.change(screen.getByRole("combobox", { name: "Sort tests" }), { target: { value: "az" } });
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("Alpha");
    expect(within(group).getByRole("button", { name: "Reading" })).toHaveAttribute("aria-pressed", "true");
  });

  it("uses the real Full Mock prerequisites without treating missing durations as ready", async () => {
    const complete = { ...detail, modules: [...detail.modules, speakingModule] };
    const noDuration = { ...complete, id: crypto.randomUUID(), test_id: crypto.randomUUID(), modules: complete.modules.map(m => m.module_type === "READING" ? { ...m, recommended_duration_seconds: null } : m) };
    const shortReading = { ...complete, id: crypto.randomUUID(), test_id: crypto.randomUUID(), modules: complete.modules.map(m => m.module_type === "READING" ? { ...m, question_count: 12 } : m) };
    vi.mocked(getTests).mockResolvedValue([
      { ...publishedTest, published_detail: complete },
      { ...publishedTest, id: noDuration.test_id, title: "Missing duration", versions: [noDuration], published_detail: noDuration },
      { ...publishedTest, id: shortReading.test_id, title: "Short reading", versions: [shortReading], published_detail: shortReading },
    ]);
    render(await LibraryPage());
    fireEvent.click(within(screen.getByRole("group", { name: "Filter tests by skill" })).getByRole("button", { name: "Full Mock" }));
    expect(screen.getByRole("heading", { name: "Short reading" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Missing duration" })).not.toBeInTheDocument();
    expect(screen.getByText(/do not produce an official band/i)).toBeInTheDocument();
    expect(screen.queryByText(/difficulty|popular|recommended for you/i)).not.toBeInTheDocument();
    expect(document.querySelector(".practice-library img")).toBeNull();
  });

  it("excludes archived, mismatched and draft details and keeps the newest eligible version", () => {
    const newer = { ...detail, id: crypto.randomUUID(), version_number: 3 };
    const draft = { ...detail, id: crypto.randomUUID(), version_number: 4, status: "DRAFT" as const };
    const archived = { ...publishedTest, id: crypto.randomUUID(), title: "Archived", archived_at: "2026-01-01" };
    render(<LibraryContent items={[
      { test: publishedTest, version: detail, detail },
      { test: publishedTest, version: newer, detail: newer },
      { test: publishedTest, version: draft, detail: draft },
      { test: archived, version: detail, detail },
      { test: { ...publishedTest, id: "mismatch", title: "Mismatch" }, version: detail, detail },
    ]} />);
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Open test" })).toHaveAttribute("href", `/library/${newer.id}`);
    expect(screen.queryByText("Archived")).not.toBeInTheDocument();
    expect(screen.queryByText("Mismatch")).not.toBeInTheDocument();
  });

  it("shows partial detail failures alongside valid cards and does not hide full catalog failures as empty", async () => {
    const missing = { ...publishedTest, id: crypto.randomUUID(), title: "Missing detail", versions: [{ ...publishedTest.versions[0], id: crypto.randomUUID() }] };
    vi.mocked(getTests).mockResolvedValue([{ ...publishedTest, published_detail: detail }, missing]);
    vi.mocked(getVersion).mockRejectedValue(new Error("network"));
    const view = render(await LibraryPage());
    expect(screen.getByRole("alert")).toHaveTextContent("Some practice content could not be loaded");
    expect(screen.getByRole("heading", { name: publishedTest.title })).toBeInTheDocument();
    view.unmount();
    vi.mocked(getTests).mockRejectedValue(new Error("network"));
    render(await LibraryPage());
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("No published tests yet")).not.toBeInTheDocument();
  });

  it("preserves community attribution and filter state when switching language", async () => {
    window.localStorage.clear();
    vi.mocked(getTests).mockResolvedValue([{ ...publishedTest, origin: "TEACHER", owner_display_name: "Linh", published_detail: detail }]);
    renderWithLocale(await LibraryPage());
    expect(screen.getByText("Community · contributed by Linh")).toBeInTheDocument();
    const search = screen.getByRole("textbox", { name: "Search the test library" });
    fireEvent.change(search, { target: { value: "Fictional" } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { name: "Thư viện đề" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Tìm kiếm trong thư viện đề" })).toBe(search);
    expect(search).toHaveValue("Fictional");
    expect(getVersion).not.toHaveBeenCalled();
  });

  it("uses only the newest published version returned by the public catalog", async () => {
    const newer = { ...detail, id: crypto.randomUUID(), version_number: 5 };
    const privateDraft = { ...detail, id: crypto.randomUUID(), version_number: 6, status: "DRAFT" as const };
    vi.mocked(getTests).mockResolvedValue([{ ...publishedTest, versions: [detail, newer, privateDraft], published_detail: newer }]);
    render(await LibraryPage());
    expect(screen.getByRole("link", { name: "Open test" })).toHaveAttribute("href", `/library/${newer.id}`);
    expect(getVersion).not.toHaveBeenCalled();
  });

  it("does not expose a direct version rejected by public eligibility", async () => {
    vi.mocked(getVersion).mockRejectedValue(new Error("not available"));
    vi.mocked(notFound).mockImplementationOnce(() => { throw new Error("NOT_FOUND"); });
    await expect(TestVersionLibraryPage({ params: Promise.resolve({ versionId }) })).rejects.toThrow("NOT_FOUND");
    expect(getVersion).toHaveBeenCalledWith(versionId, expect.any(Function), { publicOnly: true });
    expect(getTest).not.toHaveBeenCalled();
  });

  it("does not invent Writing duration on the detail screen", async () => {
    vi.mocked(getVersion).mockResolvedValue({ ...detail, modules: detail.modules.map(module => module.module_type === "WRITING" ? { ...module, recommended_duration_seconds: null } : module) });
    render(await TestVersionLibraryPage({ params: Promise.resolve({ versionId }) }));
    const writing = screen.getByText("Writing practice").closest("article")!;
    expect(within(writing).getByText("Not set")).toBeInTheDocument();
    expect(within(writing).queryByText("60 min")).not.toBeInTheDocument();
  });

  it("uses scoped theme tokens and responsive grid breakpoints", () => {
    const css = readFileSync("src/features/practice/practice-library.css", "utf8");
    expect(css).toContain("var(--surface)");
    expect(css).toContain("var(--ink)");
    expect(css).toContain("var(--accent)");
    expect(css).toContain("max-width: 1024px");
    expect(css).toContain("max-width: 560px");
    expect(css).toContain("grid-template-columns: minmax(0, 1fr)");
  });

});
