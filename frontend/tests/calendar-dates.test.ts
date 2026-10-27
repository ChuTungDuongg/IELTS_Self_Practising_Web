import { describe, expect, it } from "vitest";
import { addDays, calendarMonth, civilDate, dayKey, moveMonth, weekStart } from "@/features/classrooms/scheduling/calendar-dates";

describe("local classroom calendar dates", () => {
  it.each(["2026-02-01", "2028-02-01", "2026-12-01", "2027-01-01", "2026-03-01", "2026-11-01"])("builds complete Monday-to-Sunday weeks for %s", key => {
    const range = calendarMonth(key);
    expect(range.days[0].getDay()).toBe(1);
    expect(range.days.at(-1)!.getDay()).toBe(0);
    expect(range.days.length % 7).toBe(0);
    expect(range.days.length).toBeLessThanOrEqual(42);
    expect(range.gridEnd.valueOf() - range.start.valueOf()).toBeLessThan(93 * 86400000);
    const days = range.days.filter(day => day.getMonth() === range.first.getMonth());
    expect(days).toHaveLength(new Date(range.end.getFullYear(), range.end.getMonth(), 0).getDate());
    expect(days[0].getDate()).toBe(1);
    expect(new Set(range.days.map(dayKey)).size).toBe(range.days.length);
    expect(range.gridEnd.getHours()).toBe(0);
  });
  it("handles leap days, end-of-month clamping and year rollover", () => {
    expect(moveMonth("2028-01-31", 1)).toBe("2028-02-29");
    expect(moveMonth("2026-01-31", 1)).toBe("2026-02-28");
    expect(moveMonth("2026-12-31", 1)).toBe("2027-01-31");
    expect(dayKey(weekStart(civilDate("2026-11-01")))).toBe("2026-10-26");
  });
  it("preserves local civil days and midnight across daylight-saving transitions", () => {
    for (const key of ["2026-03-08", "2026-11-01"]) {
      const before = civilDate(key), after = addDays(before, 1);
      expect(dayKey(before)).toBe(key);
      expect(before.getHours()).toBe(0); expect(after.getHours()).toBe(0);
      expect(after.getDate()).toBe(before.getDate() + 1);
      expect(after.valueOf() - before.valueOf()).toBe(86400000 + (after.getTimezoneOffset() - before.getTimezoneOffset()) * 60000);
    }
  });
});
