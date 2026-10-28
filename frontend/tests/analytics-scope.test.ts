import { describe, expect, it } from "vitest";
import { analyticsPeriod } from "@/features/analytics/analytics-scope";
import { getAnalytics } from "@/lib/api/analytics";

describe("Analytics calendar scope", () => {
  it("includes today in seven Vietnamese calendar days using a half-open UTC interval", () => {
    expect(analyticsPeriod("7", "2026-10-29T02:00:00Z")).toEqual({
      start: "2026-10-22T17:00:00.000Z", end: "2026-10-29T17:00:00.000Z",
    });
  });
  it("uses the application calendar across a UTC date boundary and leap day", () => {
    expect(analyticsPeriod("30", "2024-03-01T18:00:00Z")).toEqual({
      start: "2024-02-01T17:00:00.000Z", end: "2024-03-02T17:00:00.000Z",
    });
    const range = analyticsPeriod("90", "2026-10-29T02:00:00Z");
    expect((Date.parse(range.end!) - Date.parse(range.start!)) / 86400000).toBe(90);
    expect(analyticsPeriod("ALL", "2026-10-29T02:00:00Z")).toEqual({});
  });
  it("sends skill and encoded boundaries together while retaining legacy requester support", async () => {
    const payload = { total_finalized_attempts: 0, total_active_seconds: 0, average_attempt_seconds: null,
      bands: {}, completed_full_mocks: 0, latest_project_overall: null, latest_full_mock: null,
      trends: [], question_types: [], weak_areas: [], attempts: [], content_timing: [] };
    const paths: string[] = [];
    const request = async <T>(path: string): Promise<T> => { paths.push(path); return payload as T; };
    await getAnalytics("READING", request, { start: "2026-10-01T00:00:00Z", end: "2026-11-01T00:00:00Z" });
    const params = new URLSearchParams(paths[0].split("?")[1]);
    expect(params.get("skill")).toBe("READING");
    expect(params.get("start")).toBe("2026-10-01T00:00:00Z");
    expect(params.get("end")).toBe("2026-11-01T00:00:00Z");
    await getAnalytics(undefined, request);
    expect(paths[1]).toBe("/analytics");
  });
});
