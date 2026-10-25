import { describe, expect, it } from "vitest";
import { crossedStorySnap, storyPosition } from "@/components/home/gravity/story-progress";

describe("homepage chapter position", () => {
  const sections = [{ start: 0, height: 700 }, { start: 700, height: 900 }, { start: 1600, height: 1050 }, { start: 2650, height: 900 }];

  it("highlights the visible chapter before its top passes behind the fixed header", () => {
    expect(storyPosition(560, 900, sections)).toMatchObject({ progress: .8, active: 1 });
    expect(storyPosition(1480, 900, sections).active).toBe(2);
    expect(storyPosition(2530, 900, sections).active).toBe(3);
  });

  it("keeps animation progress continuous across unequal phone section heights", () => {
    expect(storyPosition(699, 844, sections).progress).toBeCloseTo(699 / 700);
    expect(storyPosition(700, 844, sections).progress).toBe(1);
    expect(storyPosition(2050, 844, sections).progress).toBeCloseTo(2 + 450 / 1050);
    expect(storyPosition(5000, 844, sections)).toEqual({ progress: 4, active: 3 });
  });

  it("snaps only after crossing the approach line in the scroll direction", () => {
    const anchors = [0, 700, 1600, 2650];
    const threshold = 300;
    expect(crossedStorySnap(300, 399, anchors, threshold)).toBeNull();
    expect(crossedStorySnap(399, 400, anchors, threshold)).toEqual({ index: 1, top: 700 });
    expect(crossedStorySnap(700, 750, anchors, threshold)).toBeNull();
    expect(crossedStorySnap(351, 301, anchors, threshold)).toBeNull();
    expect(crossedStorySnap(301, 300, anchors, threshold)).toEqual({ index: 0, top: 0 });
  });

  it("selects the last threshold crossed by a large scroll movement", () => {
    const anchors = [0, 700, 1600, 2650];
    expect(crossedStorySnap(0, 2400, anchors, 300)).toEqual({ index: 3, top: 2650 });
    expect(crossedStorySnap(3000, 0, anchors, 300)).toEqual({ index: 0, top: 0 });
    expect(crossedStorySnap(2800, 2900, anchors, 300)).toBeNull();
  });
});
