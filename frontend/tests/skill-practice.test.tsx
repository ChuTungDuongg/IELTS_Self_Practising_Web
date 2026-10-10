import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PracticePage from "@/app/practice/page";
import { AppShell } from "@/components/ui/app-shell";
import { getTests, getVersion } from "@/lib/api/tests";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { versionDetailSchema, type TestSummary, type VersionDetail } from "@/lib/api/schema";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/practice" }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { display_name: "Learner", role: "USER" }, loading: false }) }));
vi.mock("@/lib/api/tests", () => ({ getTests: vi.fn(), getVersion: vi.fn() }));
vi.mock("@/lib/api/attempts", () => ({ startAttempt: vi.fn() }));

const id = (n: number) => `11111111-1111-4111-8111-${String(n).padStart(12, "0")}`;
const version: VersionDetail = {
  id: id(2), test_id: id(1), test_title: "Fictional practice test", version_number: 1,
  status: "PUBLISHED", created_at: "2026-10-10T00:00:00Z", published_at: "2026-10-10T00:00:00Z",
  modules: [
    { id: id(3), module_type: "READING", title: null, recommended_duration_seconds: 3600,
      passage_count: 2, listening_part_count: 0, writing_task_count: 0, question_count: 6,
      reading_passages: [
        { id: id(4), title: "Fictional trees", order_index: 0, question_groups: [{ question_type: "short_answer", start_number: 1, end_number: 3, question_count: 3 }] },
        { id: id(5), title: "Fictional rivers", order_index: 1, question_groups: [
          { question_type: "short_answer", start_number: 4, end_number: 5, question_count: 2 },
          { question_type: "short_answer", start_number: 9, end_number: 9, question_count: 1 },
        ] },
      ] },
    { id: id(6), module_type: "WRITING", title: null, recommended_duration_seconds: 3600,
      passage_count: 0, listening_part_count: 0, writing_task_count: 2, question_count: 0,
      writing_tasks: [
        { id: id(7), task_number: 1, task_type: "PIE_CHART", prompt_excerpt: "Describe fictional data.", minimum_recommended_words: 150, recommended_duration_seconds: 1200 },
        { id: id(8), task_number: 2, task_type: "OPINION", prompt_excerpt: "Discuss a fictional opinion.", minimum_recommended_words: 250, recommended_duration_seconds: 2400 },
      ] },
    { id: id(9), module_type: "LISTENING", title: null, recommended_duration_seconds: 1800,
      passage_count: 0, listening_part_count: 1, writing_task_count: 0, question_count: 10,
      listening_sections: [{ title: "Fictional listening section", order_index: 0, question_groups: [{ question_type: "short_answer", start_number: 1, end_number: 10 }] }] },
  ],
};
const test: TestSummary = {
  id: id(1), title: version.test_title, description: null, archived_at: null,
  source_label: null, test_number: null, created_at: version.created_at, updated_at: version.created_at,
  versions: [version],
};

describe("Skill practice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getTests).mockResolvedValue([test]);
    vi.mocked(getVersion).mockResolvedValue(version);
    vi.mocked(startAttempt).mockResolvedValue({ attempt_id: id(99) } as never);
  });

  it("adds authenticated workspace navigation in order with active route", () => {
    render(<AppShell>Content</AppShell>);
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Overview", "Test library", "Skill practice", "Attempt history", "Analytics"]);
    expect(screen.getByRole("link", { name: "Skill practice" })).toHaveAttribute("aria-current", "page");
  });

  it("uses published non-archived available versions and groups multiple tests", async () => {
    const other = { ...test, id: id(11), title: "Another fictional test", versions: [{ ...version, id: id(12) }] };
    vi.mocked(getTests).mockResolvedValue([test, other,
      { ...test, id: id(20), archived_at: version.created_at, versions: [{ ...version, id: id(21) }] },
      { ...test, id: id(30), versions: [{ ...version, id: id(31), status: "DRAFT" }] },
      { ...test, id: id(40), versions: [{ ...version, id: id(41) }] },
    ]);
    vi.mocked(getVersion).mockImplementation(async (versionId) => {
      if (versionId === id(41)) throw new Error("Unavailable");
      return versionId === id(12) ? { ...version, id: id(12), test_id: id(11), test_title: other.title } : version;
    });
    render(await PracticePage());
    expect(screen.getByRole("heading", { name: test.title })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: other.title })).toBeInTheDocument();
    expect(vi.mocked(getVersion).mock.calls.map(([value]) => value)).toEqual([id(2), id(12), id(41)]);
    expect(screen.getAllByRole("button", { name: "Start focused practice" })).toHaveLength(4);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Reading", "Writing"]);
  });

  it("shows accurate counts without inventing ranges for gaps, with Reading timers", async () => {
    render(await PracticePage());
    const cards = screen.getAllByRole("article");
    expect(within(cards[0]).getByText("Questions 1–3 · 3 questions")).toBeInTheDocument();
    expect(within(cards[1]).getByText("3 questions")).toBeInTheDocument();
    expect(screen.queryByText(/Questions 4–9/)).not.toBeInTheDocument();
    for (const select of screen.getAllByRole("combobox")) {
      expect(select).toHaveValue("1200");
      expect([...((select as HTMLSelectElement).options)].map((option) => option.textContent)).toEqual(["20 minutes", "25 minutes", "30 minutes", "Count up"]);
    }
    fireEvent.change(within(cards[1]).getByRole("combobox"), { target: { value: "1500" } });
    fireEvent.click(within(cards[1]).getByRole("button"));
    expect(startAttempt).toHaveBeenCalledWith({ test_version_id: id(2), module: "READING", scope: "FOCUSED_UNIT", focused_unit: { kind: "READING_PASSAGE", id: id(5) }, timer: { mode: "COUNTDOWN", duration_seconds: 1500 } });
    await act(async () => {});
    expect(push).toHaveBeenCalledWith(`/attempt/${id(99)}`);
  });

  it("does not turn a gap inside one group into a fictitious range/count", async () => {
    vi.mocked(getVersion).mockResolvedValue({ ...version, modules: [{ ...version.modules[0], reading_passages: [{ ...version.modules[0].reading_passages![0], question_groups: [{ question_type: "short_answer", start_number: 1, end_number: 9, question_count: 2 }] }] }] });
    render(await PracticePage());
    expect(screen.getByText("2 questions")).toBeInTheDocument();
    expect(screen.queryByText(/Questions 1–9/)).not.toBeInTheDocument();
  });

  it.each([1, 2])("starts Writing Task %i with its ID, default and count-up support", async (taskNumber) => {
    render(await PracticePage());
    fireEvent.click(screen.getByRole("tab", { name: "Writing" }));
    const card = screen.getByRole("heading", { name: `Task ${taskNumber}` }).closest("article")!;
    const select = within(card).getByRole("combobox") as HTMLSelectElement;
    expect(select).toHaveValue(taskNumber === 1 ? "1200" : "2400");
    expect([...select.options].map((option) => option.textContent)).toEqual(["20 minutes", "25 minutes", "30 minutes", "35 minutes", "40 minutes", "Count up"]);
    expect(within(card).getByText(taskNumber === 1 ? "Pie chart" : "Opinion / Agree or disagree")).toBeInTheDocument();
    expect(within(card).getByText(`Recommended ${taskNumber === 1 ? 150 : 250}+ words`)).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "count-up" } });
    fireEvent.click(within(card).getByRole("button"));
    expect(startAttempt).toHaveBeenCalledWith({ test_version_id: id(2), module: "WRITING", scope: "FOCUSED_UNIT", focused_unit: { kind: "WRITING_TASK", id: id(taskNumber === 1 ? 7 : 8) }, timer: { mode: "COUNT_UP" } });
    await act(async () => {});
  });

  it("blocks duplicate starts and preserves timer selection after a local error", async () => {
    let reject!: (error: unknown) => void;
    vi.mocked(startAttempt).mockReturnValue(new Promise((_resolve, fail) => { reject = fail; }));
    render(await PracticePage());
    const card = screen.getAllByRole("article")[0];
    const select = within(card).getByRole("combobox");
    fireEvent.change(select, { target: { value: "1800" } });
    const button = within(card).getByRole("button");
    fireEvent.click(button); fireEvent.click(button);
    expect(startAttempt).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled(); expect(button).toHaveTextContent("Starting…");
    await act(async () => reject(new ApiError("UNAVAILABLE", "This version is unavailable.", 409)));
    expect(within(card).getByRole("alert")).toHaveTextContent("This version is unavailable.");
    expect(select).toHaveValue("1800"); expect(button).not.toBeDisabled();
  });

  it("parses the public unit IDs and metadata", () => {
    const parsed = versionDetailSchema.parse(version);
    expect(parsed.modules[0].reading_passages![0].id).toBe(id(4));
    expect(parsed.modules[0].reading_passages![0].question_groups[0].question_count).toBe(3);
    expect(parsed.modules[1].writing_tasks![0]).toMatchObject({ id: id(7), minimum_recommended_words: 150, recommended_duration_seconds: 1200 });
  });

  it("does not expose a detail that is no longer published", async () => {
    vi.mocked(getVersion).mockResolvedValue({ ...version, status: "DRAFT" });
    render(await PracticePage());
    expect(screen.getByText("No Reading passages available")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start focused practice" })).not.toBeInTheDocument();
  });
});
