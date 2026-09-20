import { describe, expect, it } from "vitest";
import { formatProjectDateTime } from "@/lib/date-time";

describe("formatProjectDateTime", () => {
  it("uses a deterministic Vietnamese project timezone and day-first format", () => {
    expect(formatProjectDateTime("2026-09-20T15:00:01Z")).toBe("20/09/2026, 22:00:01");
  });

  it("returns a stable fallback for invalid timestamps", () => {
    expect(formatProjectDateTime("not-a-date")).toBe("Invalid date");
  });
});
