import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { getAnalytics } from "@/lib/api/analytics";

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
  it("renders missing values safely and changes the skill filter", async () => {
    vi.mocked(getAnalytics).mockResolvedValue(empty);
    render(<AnalyticsDashboardView initial={empty} />);
    expect(screen.getByText("Latest overall").parentElement).toHaveTextContent("—");
    expect(screen.getByText("No official band scores yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reading" }));
    await waitFor(() => expect(getAnalytics).toHaveBeenCalledWith("READING"));
  });
});
