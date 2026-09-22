export type Option = { id: string; label: string; text: string };

export type PassageBlock = {
  id: string;
  type: "paragraph" | "heading";
  label?: string | null;
  text: string;
};

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
  image_asset_id?: string | null;
  image_asset?: AssetModel | null;
};

export type QuestionType =
  | "multiple_choice"
  | "multiple_choice_multiple"
  | "true_false_not_given"
  | "yes_no_not_given"
  | "text_completion"
  | "matching_headings"
  | "matching"
  | "matching_information"
  | "matching_features"
  | "matching_sentence_endings"
  | "summary_completion_word_list"
  | "plan_labelling"
  | "map_labelling"
  | "diagram_labelling"
  | "form_completion"
  | "note_completion"
  | "table_completion"
  | "flow_chart_completion"
  | "summary_completion"
  | "sentence_completion"
  | "short_answer";

export type AssetModel = {
  id: string;
  original_name: string;
  mime_type: string;
  file_size: number;
  content_url: string;
};

export type TextCompletionSegment = {
  id: string;
  type: "TEXT" | "GAP";
  text?: string;
  question_id?: string;
};

export type TextCompletionBlock = { id: string; segments: TextCompletionSegment[] };
export type TextCompletionLayout = {
  mode: "SENTENCE" | "PASSAGE";
  blocks: TextCompletionBlock[];
};

export type TableCompletionTextSegment = {
  id: string;
  type: "TEXT";
  text: string;
};

export type TableCompletionGapSegment = {
  id: string;
  type: "GAP";
  question_id: string;
};

export type TableCompletionSegment = TableCompletionTextSegment | TableCompletionGapSegment;
export type TableCompletionCell = { id: string; segments: TableCompletionSegment[] };
export type TableCompletionRow = { id: string; cells: TableCompletionCell[] };
export type TableCompletionColumn = { id: string; label: string };
export type TableCompletionLayout = {
  kind: "TABLE";
  title?: string;
  columns: TableCompletionColumn[];
  rows: TableCompletionRow[];
  nodes: [];
};

export type DiagramBoxGeometry = {
  x: number;
  y: number;
  width: number;
};

export type DiagramArrowGeometry = {
  start_x: number;
  start_y: number;
  end_x: number;
  end_y: number;
};

export type DiagramCanvasItem = {
  id: string;
  question_id: string;
  box: DiagramBoxGeometry;
  arrow: DiagramArrowGeometry;
};

export type DiagramLabellingConfig = {
  items: DiagramCanvasItem[];
};

export type ExamQuestion = Omit<QuestionModel, "answer_key"> & {
  id: string;
  value?: unknown;
  flagged?: boolean;
};

export type ExamGroup = Omit<QuestionGroupModel, "questions"> & {
  id: string;
  questions: ExamQuestion[];
};
