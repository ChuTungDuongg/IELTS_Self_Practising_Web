import type { QuestionGroupModel, TextCompletionLayout } from "./types";

/** Diagnose without repairing, renumbering, or discarding author data. */
export function textCompletionIntegrityErrors(group: QuestionGroupModel): string[] {
  const layout = group.config as unknown as TextCompletionLayout;
  const errors = new Set<string>();
  const blockIds = new Set<string>();
  const segmentIds = new Set<string>();
  const questionIds = new Set(group.questions.map((question) => question.id));
  const references = new Map<string, number>();
  if (questionIds.has(undefined) || questionIds.size !== group.questions.length) {
    errors.add("Completion questions must have unique identities.");
  }
  for (const block of layout.blocks) {
    if (!block.id || blockIds.has(block.id)) errors.add("Completion sentences must have unique identities.");
    blockIds.add(block.id);
    for (const segment of block.segments) {
      if (!segment.id || segmentIds.has(segment.id)) errors.add("Completion text segments and gaps must have unique identities.");
      segmentIds.add(segment.id);
      if (segment.type !== "GAP") continue;
      if (!segment.question_id || !questionIds.has(segment.question_id)) {
        errors.add("One completion gap is no longer linked to its question. Select the gap to link it explicitly.");
      }
      if (segment.question_id) references.set(segment.question_id, (references.get(segment.question_id) ?? 0) + 1);
    }
  }
  if ([...references.values()].some((count) => count > 1)) errors.add("More than one completion gap is linked to the same question. Select a gap to correct its link.");
  if (group.questions.some((question) => !question.id || !references.has(question.id))) errors.add("One completion question has no gap. Link it to a gap before saving; its answer has been preserved.");
  return [...errors];
}
