type NumberedQuestion = { number: number; config: Record<string, unknown> };
type NumberedGroup = { question_type: string; questions: NumberedQuestion[] };

export function questionSpan(questionType: string, config: Record<string, unknown>): number {
  if (questionType !== "multiple_choice_multiple") return 1;
  const required = config.min_selections;
  return Number.isInteger(required) && Number(required) > 0 && required === config.max_selections ? Number(required) : 1;
}

export function questionNumbers(group: NumberedGroup): number[] {
  return group.questions.flatMap((question) => Array.from(
    { length: questionSpan(group.question_type, question.config) },
    (_, offset) => question.number + offset,
  ));
}

export function groupQuestionCount(group: NumberedGroup): number {
  return questionNumbers(group).length;
}

export function groupQuestionRange(group: NumberedGroup): string {
  const numbers = questionNumbers(group);
  if (!numbers.length) return "—";
  const start = Math.min(...numbers);
  const end = Math.max(...numbers);
  return start === end ? `Q${start}` : `Q${start}–${end}`;
}

export function completedQuestionSlots(questionType: string, config: Record<string, unknown>, value: unknown): number {
  const span = questionSpan(questionType, config);
  if (questionType === "multiple_choice_multiple") {
    return Array.isArray(value) ? Math.min(span, new Set(value).size) : 0;
  }
  return value !== null && value !== undefined && value !== "" ? 1 : 0;
}
