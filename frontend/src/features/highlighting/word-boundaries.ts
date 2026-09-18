export function snapToWordBoundaries(text: string, start: number, end: number): [number, number] {
  const segmenter = new Intl.Segmenter(undefined, { granularity: "word" });
  const words = Array.from(segmenter.segment(text)).filter((item) => item.isWordLike);
  const first = words.find((item) => item.index + item.segment.length > start);
  const last = [...words].reverse().find((item) => item.index < end);
  if (!first || !last) return [start, end];
  return [first.index, last.index + last.segment.length];
}
