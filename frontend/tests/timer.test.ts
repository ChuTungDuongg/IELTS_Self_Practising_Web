import { describe, expect, it } from "vitest";
import { elapsedSeconds, estimateServerOffset, formatDuration, remainingSeconds } from "@/features/exam/timer";

describe("server-derived timers", () => {
  it("derives remaining time from timestamps rather than interval ticks", () => {
    expect(remainingSeconds("2026-01-01T00:01:00.000Z", 0, Date.parse("2026-01-01T00:00:10.000Z"))).toBe(50);
  });

  it("derives elapsed time and formats hours", () => {
    expect(elapsedSeconds("2026-01-01T00:00:00.000Z", 0, Date.parse("2026-01-01T01:13:42.000Z"))).toBe(4422);
    expect(formatDuration(4422)).toBe("01:13:42");
  });

  it("estimates server clock offset", () => {
    expect(estimateServerOffset("2026-01-01T00:00:05.000Z", Date.parse("2026-01-01T00:00:00.000Z"))).toBe(5000);
  });
});
