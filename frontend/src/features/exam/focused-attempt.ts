import { translate } from "@/lib/i18n/translations";
import type { TranslationFunction } from "@/lib/i18n/types";
import type { AttemptResponse } from "@/lib/api/attempts";

const english: TranslationFunction = (key, params) => translate("en", key, params);

export function focusedUnitLabel(attempt: Pick<AttemptResponse, "scope" | "focused_unit">, t: TranslationFunction = english): string | null {
  if (attempt.scope !== "FOCUSED_UNIT" || !attempt.focused_unit) return null;
  const { kind, order_index, title } = attempt.focused_unit;
  const label = t(kind === "READING_PASSAGE" ? "common.passageNumber" : kind === "LISTENING_PART" ? "common.sectionNumber" : "common.taskNumber", { number: order_index + 1 });
  return title ? `${label} · ${title}` : label;
}

export function accuracyLabel(raw: number | null, max: number | null, t: TranslationFunction = english): string | null {
  return raw !== null && max !== null && max > 0 ? t("common.accuracy", { value: (raw / max * 100).toFixed(1) }) : null;
}
