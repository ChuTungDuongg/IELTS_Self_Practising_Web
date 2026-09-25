import type { QuestionModel } from "./types";

export function GapQuestionNavigator({
  questions,
  selectedQuestionId,
  onSelect,
}: {
  questions: QuestionModel[];
  selectedQuestionId: string;
  onSelect: (questionId: string) => void;
}) {
  const index = questions.findIndex((question) => question.id === selectedQuestionId);
  if (index < 0) return null;

  return (
    <nav className="flex flex-wrap items-center gap-3 py-3" aria-label="Answer key questions">
      <button type="button" className="btn btn-secondary" disabled={index === 0} onClick={() => onSelect(questions[index - 1].id!)}>← Previous</button>
      <span className="text-sm font-semibold">Q{questions[index].number} · {index + 1} of {questions.length}</span>
      <button type="button" className="btn btn-secondary" disabled={index === questions.length - 1} onClick={() => onSelect(questions[index + 1].id!)}>Next →</button>
    </nav>
  );
}
