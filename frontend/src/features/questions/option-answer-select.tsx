"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";
import type { ExamQuestion, Option } from "./types";

/** UUID-valued option control shared by matching and inline word-list gaps. */
export function OptionAnswerSelect({ question, options, value, disabled, onAnswer, placeholder, className }: {
  question: ExamQuestion;
  options: Option[];
  value: unknown;
  disabled?: boolean;
  onAnswer?: (questionId: string, value: string | string[]) => void;
  placeholder: string;
  className: string;
}) {
  const { t } = useTranslation();
  return <select
    aria-label={t("runner.question", { number: question.number })}
    disabled={disabled}
    value={String(value ?? "")}
    onChange={(event) => onAnswer?.(question.id, event.target.value)}
    className={className}
  >
    <option value="">{placeholder}</option>
    {options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}
  </select>;
}
