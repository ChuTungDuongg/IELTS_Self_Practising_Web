import { describe, expect, it } from "vitest";
import { countWords } from "@/features/writing/word-count";

describe("countWords", () => {
  it("counts words across repeated whitespace and punctuation", () => {
    expect(countWords("  The chart, illustrates\nsolar-power growth. ")).toBe(5);
  });

  it("handles apostrophes without splitting a word", () => {
    expect(countWords("It’s a city's plan." )).toBe(4);
  });
});
