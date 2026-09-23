import { beforeEach, describe, expect, it, vi } from "vitest";
import { revealQuestionChip, scrollQuestionIntoPane } from "@/features/exam/question-navigation";

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, right: left + width, bottom: top + height, width, height, x: left, y: top, toJSON: () => ({}) } as DOMRect;
}

describe("local exam navigation geometry", () => {
  const scrolls: Array<{ element: HTMLElement; options: ScrollToOptions }> = [];

  beforeEach(() => {
    scrolls.length = 0;
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(function (this: HTMLElement, options: ScrollToOptions) { scrolls.push({ element: this, options }); }),
    });
  });

  it("centers a question relative to its pane and clamps at the end", () => {
    const pane = document.createElement("div");
    const target = document.createElement("div");
    pane.scrollTop = 100;
    Object.defineProperties(pane, { clientHeight: { value: 400 }, scrollHeight: { value: 1200 } });
    pane.getBoundingClientRect = () => rect(30, 50, 500, 400);
    target.getBoundingClientRect = () => rect(50, 350, 300, 100);
    scrollQuestionIntoPane(pane, target);
    expect(scrolls).toEqual([{ element: pane, options: { top: 250, behavior: "auto" } }]);
    pane.scrollTop = 700;
    scrollQuestionIntoPane(pane, target);
    expect(scrolls[1].options.top).toBe(800);
  });

  it("reveals only clipped chips using the horizontal strip", () => {
    const strip = document.createElement("nav");
    const chip = document.createElement("button");
    strip.scrollLeft = 80;
    strip.getBoundingClientRect = () => rect(100, 500, 300, 50);
    chip.getBoundingClientRect = () => rect(150, 505, 40, 35);
    revealQuestionChip(strip, chip);
    expect(scrolls).toHaveLength(0);
    chip.getBoundingClientRect = () => rect(65, 505, 40, 35);
    revealQuestionChip(strip, chip);
    expect(scrolls[0]).toEqual({ element: strip, options: { left: 45, behavior: "auto" } });
    chip.getBoundingClientRect = () => rect(390, 505, 45, 35);
    revealQuestionChip(strip, chip);
    expect(scrolls[1]).toEqual({ element: strip, options: { left: 115, behavior: "auto" } });
    expect(scrolls.every((item) => item.options.top === undefined)).toBe(true);
  });
});
