import type { QuestionType } from "./types";

export const questionTypeLabels: Record<QuestionType, string> = {
  multiple_choice: "Multiple Choice — Single",
  multiple_choice_multiple: "Multiple Choice — Multiple",
  true_false_not_given: "True / False / Not Given",
  yes_no_not_given: "Yes / No / Not Given",
  text_completion: "Text Completion",
  matching_headings: "Matching Headings",
  matching: "Matching",
  matching_information: "Matching Information",
  matching_features: "Matching Features",
  matching_sentence_endings: "Matching Sentence Endings",
  summary_completion_word_list: "Summary Completion — Word List",
  plan_labelling: "Plan Labelling",
  map_labelling: "Map Labelling",
  diagram_labelling: "Diagram Label Completion",
  form_completion: "Form Completion",
  note_completion: "Note Completion",
  table_completion: "Table Completion",
  flow_chart_completion: "Flow-chart Completion",
  summary_completion: "Summary Completion — Text",
  sentence_completion: "Sentence Completion",
  short_answer: "Short Answer",
};

export function questionTypeLabel(type: string): string {
  return type in questionTypeLabels ? questionTypeLabels[type as QuestionType] : type.replaceAll("_", " ");
}
