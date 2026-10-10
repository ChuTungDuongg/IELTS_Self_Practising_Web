"use client";

import type { SummaryUnit } from "./content-summary";
import { questionTypeLabel } from "@/features/questions/question-type-meta";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { questionTypeTranslationKeys, writingTaskTranslationKeys } from "@/lib/i18n/translations";

export function ContentSummary({ units }: { units: SummaryUnit[] }) {
  const { t } = useTranslation();
  if (!units.length) return <p className="mt-4 text-sm text-[var(--muted)]">{t("common.noContent")}</p>;
  return <div className="mt-4 space-y-3">
    {units.map((unit) => <div key={`${unit.heading.message}-${unit.heading.params.number}`} className="border-t border-[var(--border)] pt-3">
      <p className="text-sm font-medium text-[var(--muted)]">{t(unit.heading.message, unit.heading.params)}</p>
      {unit.title ? <p className="mt-1 text-sm font-semibold">{unit.title}</p> : null}
      {unit.questionTypes ? <div className="mt-2 flex flex-wrap gap-1.5">{unit.questionTypes.map((type) => <span key={type} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs">{questionTypeTranslationKeys[type] ? t(questionTypeTranslationKeys[type]) : questionTypeLabel(type)}</span>)}</div> : null}
      {unit.taskType !== undefined ? <span className="mt-2 inline-block rounded-full border border-[var(--border)] px-2 py-0.5 text-xs">{t(unit.taskType ? writingTaskTranslationKeys[unit.taskType] : "common.unclassified")}</span> : null}
      {unit.excerpt ? <p className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">{unit.excerpt}</p> : null}
    </div>)}
  </div>;
}
