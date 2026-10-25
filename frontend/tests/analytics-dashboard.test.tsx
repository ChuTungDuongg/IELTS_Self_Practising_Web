import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { compareAttempts, getAnalytics, type AttemptComparison } from "@/lib/api/analytics";
import { renderWithLocale } from "./locale-test-utils";

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
    expect(screen.getAllByRole("heading", { name: "Section 2 · Đề <img> · V1" })).toHaveLength(2);
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
    expect(screen.getByText("No official band scores yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reading" }));
    await waitFor(() => expect(getAnalytics).toHaveBeenCalledWith("READING"));
  });
});
