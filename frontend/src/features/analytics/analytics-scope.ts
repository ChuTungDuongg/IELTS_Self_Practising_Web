import type { AnalyticsPeriod } from "@/lib/api/analytics";

export type AnalyticsRange = "7" | "30" | "90" | "ALL";
export const analyticsTimeZone = "Asia/Ho_Chi_Minh";

// BandPilot's calendar is UTC+7 (no daylight saving). Include today and use an
// exclusive midnight tomorrow, independent of browser/server operating timezone.
export function analyticsPeriod(range: AnalyticsRange, asOf: string): AnalyticsPeriod {
  if (range === "ALL") return {};
  const day = 86_400_000;
  const offset = 7 * 3_600_000;
  const today = Math.floor((Date.parse(asOf) + offset) / day) * day - offset;
  return { start: new Date(today - (Number(range) - 1) * day).toISOString(), end: new Date(today + day).toISOString() };
}
