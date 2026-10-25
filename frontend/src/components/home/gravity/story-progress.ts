type SectionSpan = { start: number; height: number };

export function storyPosition(offset: number, viewportHeight: number, sections: SectionSpan[]) {
  let progress = 0, active = 0;
  const readingLine = Math.max(0, offset) + viewportHeight * .45;
  sections.forEach(({ start, height }, index) => {
    if (offset >= start) progress = index + Math.min(1, (offset - start) / Math.max(1, height));
    if (readingLine >= start) active = index;
  });
  return { progress, active };
}

/** Return the chapter whose approach line was crossed by this scroll movement. */
export function crossedStorySnap(previous: number, current: number, anchors: number[], threshold: number) {
  if (current === previous || threshold <= 0) return null;
  let crossed: { index: number; top: number } | null = null;
  if (current > previous) {
    for (let index = 1; index < anchors.length; index++) {
      const line = anchors[index] - threshold;
      if (previous < line && current >= line) crossed = { index, top: anchors[index] };
    }
  } else {
    for (let index = anchors.length - 1; index >= 0; index--) {
      const line = anchors[index] + threshold;
      if (previous > line && current <= line) crossed = { index, top: anchors[index] };
    }
  }
  return crossed;
}
