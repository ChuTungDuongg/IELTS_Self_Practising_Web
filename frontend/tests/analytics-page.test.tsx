import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import AnalyticsPage from "@/app/analytics/page";
import { getAnalytics } from "@/lib/api/analytics";
import { serverApiRequest } from "@/lib/api/server-client";

vi.mock("@/lib/api/analytics", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/api/analytics")>(), getAnalytics: vi.fn(),
}));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));

beforeEach(() => { vi.resetAllMocks(); window.localStorage.clear(); });

it("uses the same all-history scope for server data and initial client controls", async () => {
  vi.mocked(getAnalytics).mockResolvedValue({
    total_finalized_attempts: 2, total_active_seconds: 120, average_attempt_seconds: 60,
    bands: {}, completed_full_mocks: 0, latest_project_overall: null, latest_full_mock: null,
    trends: [], question_types: [], weak_areas: [], attempts: [], content_timing: [],
  });
  render(await AnalyticsPage());
  expect(getAnalytics).toHaveBeenCalledExactlyOnceWith(undefined, serverApiRequest);
  expect(screen.getByRole("button", { name: "All history" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Finalized attempts").closest("article")).toHaveTextContent("2");
});

it("propagates a failed server fetch to the existing retry error boundary instead of empty data", async () => {
  vi.mocked(getAnalytics).mockRejectedValue(new Error("Fictional backend unavailable"));
  await expect(AnalyticsPage()).rejects.toThrow("Fictional backend unavailable");
});
