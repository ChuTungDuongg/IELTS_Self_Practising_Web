import { describe, expect, it } from "vitest";
import { snapToWordBoundaries } from "@/features/highlighting/word-boundaries";

describe("snapToWordBoundaries", () => {
  it("expands a partial selection to complete words", () => {
    const text = "The Industrial Revolution changed society.";
    expect(snapToWordBoundaries(text, 6, 24)).toEqual([4, 25]);
  });

  it("does not include surrounding punctuation", () => {
    const text = "Energy: solar power, became common.";
    expect(snapToWordBoundaries(text, 9, 20)).toEqual([8, 19]);
  });
});
