import { questionRegistry, type InstructionContext, type InstructionGroup, type QuestionInstruction } from "./registry";
import type { QuestionType } from "./types";

const completionQuestionTypes = new Set<QuestionType>([
  "text_completion",
  "sentence_completion",
  "summary_completion",
  "note_completion",
  "form_completion",
  "table_completion",
  "flow_chart_completion",
]);

export function isCompletionQuestionType(questionType: QuestionType): boolean {
  return completionQuestionTypes.has(questionType);
}

export function resolveQuestionGroupInstruction(
  group: InstructionGroup,
  context: InstructionContext = {},
): QuestionInstruction {
  const generated = questionRegistry[group.question_type].instruction(group, context);
  const custom = group.instruction.trim();
  return custom ? { ...generated, intro: custom } : generated;
}

export function QuestionGroupInstruction({ group, passageNumber }: { group: InstructionGroup; passageNumber?: number }) {
  const instruction = resolveQuestionGroupInstruction(group, { passageNumber });
  return (
    <div className="question-group-instruction">
      <p className="question-group-instruction-text">{instruction.intro}</p>
      {instruction.options?.length ? (
        <dl>
          {instruction.options.map((option) => (
            <div key={option.label}>
              <dt>{option.label}</dt>
              <dd>{option.description}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
