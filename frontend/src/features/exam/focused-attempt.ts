import type { AttemptResponse } from "@/lib/api/attempts";

export function focusedUnitLabel(attempt: Pick<AttemptResponse, "scope" | "focused_unit">): string | null {
  if (attempt.scope !== "FOCUSED_UNIT" || !attempt.focused_unit) return null;
  const { label, title } = attempt.focused_unit;
  return title ? `${label} · ${title}` : label;
}

export function accuracyLabel(raw: number | null, max: number | null): string | null {
  return raw !== null && max !== null && max > 0 ? `${(raw / max * 100).toFixed(1)}% accuracy` : null;
}
