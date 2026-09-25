import type { NoteCompletionLayout, QuestionGroupModel } from "./types";

export function noteCompletionGapIds(layout: NoteCompletionLayout): string[] {
  return layout.blocks.flatMap((block) => block.segments.flatMap((segment) => (
    segment.type === "GAP" ? [segment.question_id] : []
  )));
}

/** Diagnose without replacing UUID-bound author content. */
export function noteCompletionIntegrityErrors(group: QuestionGroupModel): string[] {
  const layout = group.config.layout as NoteCompletionLayout;
  const errors = new Set<string>();
  const questionIds = group.questions.map((question) => question.id).filter((id): id is string => Boolean(id));
  const blockIds = layout.blocks.map((block) => block.id);
  const segmentIds = layout.blocks.flatMap((block) => block.segments.map((segment) => segment.id));
  const gapIds = noteCompletionGapIds(layout);

  if (questionIds.length !== group.questions.length || new Set(questionIds).size !== questionIds.length) {
    errors.add("Note questions must have unique identities.");
  }
  if (blockIds.some((id) => !id) || new Set(blockIds).size !== blockIds.length) {
    errors.add("Note blocks must have unique identities.");
  }
  if (segmentIds.some((id) => !id) || new Set(segmentIds).size !== segmentIds.length) {
    errors.add("Note text segments and gaps must have unique identities.");
  }
  if (gapIds.length !== new Set(gapIds).size) {
    errors.add("Every Note question must be linked to exactly one gap.");
  }
  const questionSet = new Set(questionIds);
  const gapSet = new Set(gapIds);
  if (gapIds.some((id) => !questionSet.has(id)) || questionIds.some((id) => !gapSet.has(id))) {
    errors.add("Every Note question must be linked to exactly one gap.");
  }
  if (layout.blocks.some((block) => !block.segments.length || !block.segments.some((segment) => (
    segment.type === "GAP" || Boolean(segment.text.trim())
  )))) {
    errors.add("Note blocks cannot be empty when saved.");
  }
  if (layout.blocks.some((block) => block.indent < 0 || block.indent > 3)) {
    errors.add("Note indentation must be between 0 and 3.");
  }
  return [...errors];
}

export function normalizeNoteCompletionOrder(
  group: QuestionGroupModel,
  layout: NoteCompletionLayout,
  baseQuestionNumber?: number,
): QuestionGroupModel {
  const gapIds = noteCompletionGapIds(layout);
  const byId = new Map(group.questions.flatMap((question) => question.id ? [[question.id, question]] : []));
  const firstNumber = baseQuestionNumber
    ?? (group.questions.length ? Math.min(...group.questions.map((question) => question.number)) : 1);
  const next = { ...group, config: { ...group.config, layout } };
  const orderedQuestions = gapIds.map((id) => byId.get(id));
  const canOrder = group.questions.length === gapIds.length
    && byId.size === group.questions.length
    && new Set(gapIds).size === gapIds.length
    && orderedQuestions.every((question) => question !== undefined);
  return {
    ...next,
    questions: canOrder
      ? orderedQuestions.map((question, order_index) => ({ ...question!, number: firstNumber + order_index, order_index }))
      : group.questions,
  };
}
