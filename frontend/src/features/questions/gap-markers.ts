export const GAP_MARKER = "{{gap}}";

export function splitGapMarkers(text: string): string[] {
  return text.split(GAP_MARKER);
}
