import { describe, expect, it } from "vitest";
import { taskBandFromRawMean, writingTaskBand } from "@/features/writing/task-band";

describe("Writing task band compatibility", () => {
  it.each([[4.625, 4.5], [4.75, 5], [6.25, 6.5], [6.75, 7], [7.125, 7], [7.875, 8], [0, 0], [9, 9]])(
    "matches backend half-up rounding: %s → %s", (raw, band) => {
      expect(taskBandFromRawMean(raw)).toBe(band);
    },
  );
  it.each([null, undefined, NaN])("does not invent a band for %s", raw => {
    expect(taskBandFromRawMean(raw)).toBeNull();
  });
  it("requires all criteria for a legacy review score", () => {
    expect(writingTaskBand({ ta: 5, cc: 5, lr: 4, gra: 4.5, overall: 4.625 })).toBe(4.5);
    expect(writingTaskBand({ ta: 5, cc: 5, lr: 4, overall: 4.625 })).toBeNull();
    expect(writingTaskBand(null)).toBeNull();
    expect(writingTaskBand({ ta: 0, cc: 0, lr: 0, gra: 0, overall: 0 })).toBe(0);
  });
});
