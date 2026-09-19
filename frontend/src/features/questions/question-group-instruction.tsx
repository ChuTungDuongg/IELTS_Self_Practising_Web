import { questionRegistry, type InstructionContext, type InstructionGroup, type QuestionInstruction } from "./registry";

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
      <p>{instruction.intro}</p>
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
