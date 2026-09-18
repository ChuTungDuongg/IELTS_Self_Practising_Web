export type Option = { id: string; label: string };

export type QuestionModel = {
  id?: string;
  number: number;
  prompt: string;
  config: Record<string, unknown>;
  answer_key: Record<string, unknown>;
  explanation?: string | null;
  order_index: number;
};

export type QuestionGroupModel = {
  id?: string;
  question_type: QuestionType;
  instruction: string;
  config: Record<string, unknown>;
  order_index: number;
  questions: QuestionModel[];
};

export type QuestionType =
  | "multiple_choice"
  | "true_false_not_given"
  | "text_completion"
  | "matching_headings";

export type ExamQuestion = Omit<QuestionModel, "answer_key"> & {
  id: string;
  value?: unknown;
  flagged?: boolean;
};

export type ExamGroup = Omit<QuestionGroupModel, "questions"> & {
  id: string;
  questions: ExamQuestion[];
};
