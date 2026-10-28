import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { compareAttempts, getAnalytics, type AttemptComparison } from "@/lib/api/analytics";
import { renderWithLocale } from "./locale-test-utils";
import { readFileSync } from "node:fs";

vi.mock("@/lib/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/analytics")>();
  return { ...actual, getAnalytics: vi.fn(), compareAttempts: vi.fn() };
});

const empty = {
  total_finalized_attempts: 0, total_active_seconds: 0, average_attempt_seconds: null,
  bands: { READING: { latest: null, best: null, average: null }, LISTENING: { latest: null, best: null, average: null }, WRITING: { latest: null, best: null, average: null } },
  completed_full_mocks: 0, latest_project_overall: null, latest_full_mock: null,
  trends: [], question_types: [], weak_areas: [], attempts: [], content_timing: [],
};

describe("Analytics dashboard", () => {
  beforeEach(() => { window.localStorage.clear(); vi.resetAllMocks(); });

  it("renders one heading, four independent KPI cards and honest empty sections", () => {
    const { container } = render(<AnalyticsDashboardView initial={empty} />);
    expect(screen.getByRole("heading", { level: 1, name: "Practice analytics" })).toBeInTheDocument();
    expect(container.querySelectorAll(".analytics-kpi")).toHaveLength(4);
    expect(screen.getByText("Finalized attempts").closest("article")).toHaveTextContent("0");
    expect(screen.getByText("Active practice time").closest("article")).toHaveTextContent("00:00");
    expect(screen.getByRole("link", { name: "Start practicing" })).toHaveAttribute("href", "/library");
    expect(screen.queryByText(/\+20%|\+35%/)).not.toBeInTheDocument();
    expect(container.querySelector("polyline")).toBeNull();
  });

  it("combines date and skill scopes and keeps the committed selection after errors", async () => {
    vi.mocked(getAnalytics).mockResolvedValueOnce(empty).mockResolvedValueOnce(empty).mockRejectedValueOnce(new Error("secret"));
    render(<AnalyticsDashboardView initial={empty} asOf="2026-10-29T02:00:00Z" />);
    fireEvent.click(screen.getByRole("button", { name: "Last 7 days" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Last 7 days" })).toHaveAttribute("aria-pressed", "true"));
    expect(getAnalytics).toHaveBeenLastCalledWith(undefined, undefined, {
      start: "2026-10-22T17:00:00.000Z", end: "2026-10-29T17:00:00.000Z",
    });
    fireEvent.click(screen.getByRole("button", { name: "Reading" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Reading" })).toHaveAttribute("aria-pressed", "true"));
    expect(getAnalytics).toHaveBeenLastCalledWith("READING", undefined, {
      start: "2026-10-22T17:00:00.000Z", end: "2026-10-29T17:00:00.000Z",
    });
    fireEvent.click(screen.getByRole("button", { name: "Last 30 days" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Last 7 days" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Reading" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows real band averages, accuracy, duration and newest five activities", () => {
    const attempts = Array.from({ length: 6 }, (_, index) => ({
      attempt_id: `activity-${index}`, skill: "READING" as const, label: `Fictional ${index}`,
      test_title: `Fictional ${index}`, band_score: index ? 6.5 : null,
      finished_at: `2026-10-${String(index + 10).padStart(2, "0")}T05:00:00Z`,
    }));
    render(<AnalyticsDashboardView initial={{ ...empty, total_finalized_attempts: 6, total_active_seconds: 45360,
      average_attempt_seconds: 7560, bands: { ...empty.bands, READING: { latest: 7, best: 8, average: 6.75 } },
      question_types: [{ question_type: "matching_headings", attempted: 10, correct: 7, incorrect: 3, accuracy: 70 }], attempts }} />);
    expect(screen.getByText("Active practice time").closest("article")).toHaveTextContent("12:36:00");
    const performance = screen.getByRole("region", { name: "Average band by skill" });
    expect(performance).toHaveTextContent("6.75");
    expect(within(performance).getByRole("progressbar", { name: "Reading" })).toHaveAttribute("aria-valuenow", "6.75");
    expect(within(performance).queryByRole("progressbar", { name: "Listening" })).toBeNull();
    expect(screen.getByRole("region", { name: "Question-type accuracy" })).toHaveTextContent("70.0%");
    const recent = screen.getByRole("region", { name: "Recent activity" });
    const links = within(recent).getAllByRole("link").filter(link => link.getAttribute("href")?.startsWith("/review/"));
    expect(links).toHaveLength(5);
    expect(links[0]).toHaveAttribute("href", "/review/activity-5");
    expect(within(recent).queryByText("Fictional 0")).toBeNull();
    expect(within(screen.getByLabelText("Attempt A")).getByRole("option", { name: /Fictional 5 · Reading · 15\/10\/2026/ })).toBeInTheDocument();
  });

  it("clears pending/stale comparisons when a scope changes", async () => {
    let complete!: (value: AttemptComparison) => void;
    vi.mocked(compareAttempts).mockImplementationOnce(() => new Promise(resolve => { complete = resolve; }));
    vi.mocked(getAnalytics).mockResolvedValueOnce(empty);
    const side: AttemptComparison["left"] = { attempt_id: "one", skill: "READING", test_title: "Old scope",
      version_number: 1, band_score: 7, raw_score: 30, max_score: 40, elapsed_seconds: 60, accuracy: 75, question_types: [], writing: null };
    render(<AnalyticsDashboardView initial={{ ...empty, attempts: [side, { ...side, attempt_id: "two" }].map(item => ({
      attempt_id: item.attempt_id, skill: item.skill, label: item.test_title, band_score: item.band_score, finished_at: "2026-10-10T00:00:00Z",
    })) }} />);
    fireEvent.change(screen.getByLabelText("Attempt A"), { target: { value: "one" } });
    fireEvent.change(screen.getByLabelText("Attempt B"), { target: { value: "two" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    fireEvent.click(screen.getByRole("button", { name: "Reading" }));
    await waitFor(() => expect(screen.getByLabelText("Attempt A")).toHaveValue(""));
    await act(async () => { complete({ same_skill: true, same_test_version: true, left: side, right: { ...side, attempt_id: "two" } }); });
    expect(screen.queryByRole("heading", { name: "Old scope" })).not.toBeInTheDocument();
  });

  it("keeps weak areas at the five-graded-answer threshold", () => {
    render(<AnalyticsDashboardView initial={{ ...empty, weak_areas: [{ question_type: "short_answer", attempted: 4,
      correct: 0, incorrect: 4, accuracy: 0 }] }} />);
    expect(screen.getByRole("region", { name: "Needs attention" })).toHaveTextContent("At least 5 graded questions");
  });

  it("retries the exact failed date scope and prevents duplicate filter requests", async () => {
    let finish!: (value: typeof empty) => void;
    vi.mocked(getAnalytics).mockRejectedValueOnce(new Error("offline"));
    render(<AnalyticsDashboardView initial={{ ...empty, total_finalized_attempts: 6 }} asOf="2026-10-29T02:00:00Z" />);
    fireEvent.click(screen.getByRole("button", { name: "Last 30 days" }));
    await screen.findByRole("alert");
    expect(screen.getByText("Finalized attempts").closest("article")).toHaveTextContent("6");
    expect(screen.getByRole("button", { name: "All history" })).toHaveAttribute("aria-pressed", "true");
    vi.mocked(getAnalytics).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const retry = screen.getByRole("button", { name: "Try again" });
    fireEvent.click(retry); fireEvent.click(retry);
    expect(getAnalytics).toHaveBeenCalledTimes(2);
    expect(getAnalytics).toHaveBeenLastCalledWith(undefined, undefined, {
      start: "2026-09-29T17:00:00.000Z", end: "2026-10-29T17:00:00.000Z",
    });
    await act(async () => { finish(empty); });
    expect(screen.getByRole("button", { name: "Last 30 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("labels an actual Full Mock separately from a practice-derived overall", () => {
    const { rerender } = render(<AnalyticsDashboardView initial={{ ...empty, latest_project_overall: 6.5 }} />);
    expect(screen.getByText("Latest overall").closest("article")).toHaveTextContent("6.5");
    expect(screen.getByText("Practice-derived overall · all skills, this period")).toBeInTheDocument();
    rerender(<AnalyticsDashboardView key="mock" initial={{ ...empty, latest_project_overall: 6.5,
      latest_full_mock: { session_id: "mock", test_title: "Fictional full mock", finished_at: "2026-10-10T00:00:00Z",
        reading_band: 7, listening_band: 7, writing_band: 7, speaking_band: 7, overall_band: 7 } }} />);
    expect(screen.getByText("Latest overall").closest("article")).toHaveTextContent("7.0");
    expect(screen.getByText("Latest completed Full Mock · all skills")).toBeInTheDocument();
  });

  it("uses unavailable and not-applicable states for ungraded Writing rather than zero accuracy", async () => {
    vi.mocked(getAnalytics).mockResolvedValueOnce({ ...empty, attempts: [{ attempt_id: "writing", skill: "WRITING",
      label: "Fictional ungraded Writing", test_title: "Fictional ungraded Writing", finished_at: "2026-10-15T00:00:00Z", band_score: null }] });
    render(<AnalyticsDashboardView initial={empty} />);
    fireEvent.click(screen.getByRole("button", { name: "Writing" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Writing" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("region", { name: "Question-type accuracy" })).toHaveTextContent("assessment criteria");
    const recent = screen.getByRole("region", { name: "Recent activity" });
    expect(recent).toHaveTextContent("No band available");
    expect(recent).not.toHaveTextContent("0.0");
    expect(screen.getByRole("link", { name: /Fictional ungraded Writing/ })).toHaveAttribute("href", "/review/writing");
  });

  it("filters comparison options to the selected skill and clears B when A changes", () => {
    render(<AnalyticsDashboardView initial={{ ...empty, attempts: ["READING", "READING", "WRITING"].map((skill, index) => ({
      attempt_id: `a-${index}`, skill: skill as "READING" | "WRITING", label: `Fictional ${index}`,
      finished_at: "2026-10-10T00:00:00Z", band_score: null,
    })) }} />);
    fireEvent.change(screen.getByLabelText("Attempt A"), { target: { value: "a-0" } });
    expect(within(screen.getByLabelText("Attempt B")).queryByRole("option", { name: "Fictional 2" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Attempt B"), { target: { value: "a-1" } });
    expect(screen.getByRole("button", { name: "Compare" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Attempt A"), { target: { value: "a-2" } });
    expect(screen.getByLabelText("Attempt B")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();
  });

  it("localizes the new dashboard without refetching or changing authored titles", () => {
    renderWithLocale(<AnalyticsDashboardView initial={{ ...empty, attempts: [{ attempt_id: "s1", skill: "SPEAKING",
      label: "Fictional <authored> title", test_title: "Fictional <authored> title", band_score: null, finished_at: "2026-10-10T00:00:00Z" }] }} />);
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { level: 1, name: "Thống kê luyện tập" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "90 ngày" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("link", { name: /Fictional <authored> title/ })).toBeInTheDocument();
    expect(getAnalytics).not.toHaveBeenCalled();
  });

  it("keeps scoped theme tokens and responsive layouts without modifying the global shell", () => {
    const css = readFileSync("src/features/analytics/analytics.css", "utf8");
    expect(css).toContain(".analytics-workspace");
    expect(css).toContain("background: var(--surface)");
    expect(css).toContain("grid-template-columns: repeat(4, minmax(0, 1fr))");
    expect(css).toContain("@media (max-width: 1100px)");
    expect(css).toContain("@media (max-width: 540px)");
    expect(css).toContain("white-space: normal");
    expect(css).toContain("minmax(0, 1fr) auto");
    expect(css).toContain("prefers-reduced-motion");
    expect(css).not.toMatch(/\.app-header|:root|backdrop-filter/);
  });
  it("keeps previous results and an accurate selected filter when refreshing fails, then retries", async () => {
    vi.mocked(getAnalytics).mockRejectedValueOnce(new Error("private backend detail"));
    render(<AnalyticsDashboardView initial={{ ...empty, total_finalized_attempts: 6 }} />);
    fireEvent.click(screen.getByRole("button", { name: "Reading" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your previous results are still shown");
    expect(screen.getByText("Finalized attempts").parentElement).toHaveTextContent("6");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("private backend detail")).not.toBeInTheDocument();
    vi.mocked(getAnalytics).mockResolvedValueOnce(empty);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Reading" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("places dated attempts on a real time scale and exposes their values as text", () => {
    render(<AnalyticsDashboardView initial={{ ...empty, trends: [
      { attempt_id: "first", skill: "READING", band_score: 5, attempted_at: "2026-10-01T00:00:00Z", test_title: "First fictional test", version_number: 1 },
      { attempt_id: "second", skill: "READING", band_score: 6, attempted_at: "2026-10-02T00:00:00Z", test_title: "Second fictional test", version_number: 1 },
      { attempt_id: "last", skill: "READING", band_score: 7, attempted_at: "2026-10-11T00:00:00Z", test_title: "Last fictional test", version_number: 1 },
    ] }} />);
    const chart = screen.getByRole("img", { name: "Band score trend from 0 to 9" });
    const points = [...chart.querySelectorAll("circle")].map(point => Number(point.getAttribute("cx")));
    expect((points[1] - points[0]) / (points[2] - points[0])).toBeCloseTo(.1);
    fireEvent.click(screen.getByText("View score details"));
    expect(screen.getByRole("table")).toHaveTextContent("01 Oct 2026");
    expect(screen.getByRole("table")).toHaveTextContent("First fictional test");
    expect(screen.getByRole("table")).toHaveTextContent("7.0");
  });

  it("localizes comparison metric labels without changing authored titles or score values", async () => {
    window.localStorage.clear(); vi.clearAllMocks();
    const side: AttemptComparison["left"] = { attempt_id: "one", skill: "WRITING", test_title: "Section 2 · Đề <img>", version_number: 1, band_score: 6.5, raw_score: null, max_score: null, elapsed_seconds: 60, accuracy: null, question_types: [], writing: { task1_overall: 6, task2_overall: 6.5, ta: 6, cc: 6.5, lr: 7, gra: 6.5 } };
    const comparison: AttemptComparison = { same_skill: true, same_test_version: true, left: side, right: { ...side, attempt_id: "two" } };
    const before = JSON.stringify(comparison);
    vi.mocked(compareAttempts).mockResolvedValue(comparison);
    renderWithLocale(<AnalyticsDashboardView initial={{ ...empty, attempts: [side, comparison.right].map((item) => ({ attempt_id: item.attempt_id, skill: item.skill, label: item.test_title, band_score: item.band_score, finished_at: "2026-10-10T00:00:00Z" })) }} />);
    fireEvent.change(screen.getByLabelText("Attempt A"), { target: { value: "one" } }); fireEvent.change(screen.getByLabelText("Attempt B"), { target: { value: "two" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    await screen.findAllByText("Task 1 overall");
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getAllByText("Tổng điểm bài viết 1")[0].parentElement).toHaveTextContent("6.0");
    expect(screen.getAllByRole("heading", { name: "Section 2 · Đề <img>" })).toHaveLength(2);
    expect(JSON.stringify(comparison)).toBe(before); expect(compareAttempts).toHaveBeenCalledExactlyOnceWith("one", "two");
  });
  it("preserves comparison IDs and raw API labels across locale changes", () => {
    window.localStorage.clear(); vi.clearAllMocks();
    const initial: Parameters<typeof AnalyticsDashboardView>[0]["initial"] = { ...empty, attempts: [{ attempt_id: "one", skill: "READING", label: "Section 2 <option>", band_score: null, finished_at: "2026-10-10T00:00:00Z" }, { attempt_id: "two", skill: "READING", label: "Đề thử", band_score: null, finished_at: "2026-10-10T00:00:00Z" }] };
    const before = JSON.stringify(initial);
    renderWithLocale(<AnalyticsDashboardView initial={initial} />);
    const left = screen.getByLabelText("Attempt A"); const right = screen.getByLabelText("Attempt B");
    fireEvent.change(left, { target: { value: "one" } }); fireEvent.change(right, { target: { value: "two" } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByLabelText("Lượt làm A")).toBe(left);
    expect(left).toHaveValue("one"); expect(right).toHaveValue("two");
    expect(screen.getByRole("button", { name: "So sánh" })).toBeEnabled();
    expect(screen.getAllByRole("option", { name: "Section 2 <option>" })).toHaveLength(2);
    expect(JSON.stringify(initial)).toBe(before); expect(getAnalytics).not.toHaveBeenCalled();
  });
  it("renders missing values safely and changes the skill filter", async () => {
    vi.mocked(getAnalytics).mockResolvedValue(empty);
    render(<AnalyticsDashboardView initial={empty} />);
    expect(screen.getByText("Latest overall").parentElement).toHaveTextContent("—");
    expect(screen.getByText("No graded band scores in this period.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reading" }));
    await waitFor(() => expect(getAnalytics).toHaveBeenCalledWith("READING"));
  });
});
