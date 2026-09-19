import type { ComponentType } from "react";
import { z } from "zod";
import {
  MatchingEditor,
  MatchingHeadingsEditor,
  MultipleChoiceEditor,
  MultipleChoiceMultipleEditor,
  StructuredCompletionEditor,
  TextCompletionEditor,
  TrueFalseNotGivenEditor,
  VisualLabellingEditor,
  YesNoNotGivenEditor,
  type EditorProps,
} from "./editors";
import {
  MatchingHeadingsRenderer,
  MatchingRenderer,
  MultipleChoiceMultipleRenderer,
  MultipleChoiceRenderer,
  StructuredCompletionRenderer,
  TextCompletionRenderer,
  TrueFalseNotGivenRenderer,
  VisualLabellingRenderer,
  YesNoNotGivenRenderer,
  type RendererProps,
} from "./renderers";
import type { QuestionGroupModel, QuestionType } from "./types";

export type QuestionInstruction = {
  intro: string;
  options?: Array<{ label: string; description: string }>;
};

export type InstructionContext = { passageNumber?: number };
export type InstructionGroup = Pick<QuestionGroupModel, "question_type" | "instruction" | "config"> & {
  questions: Array<{ config: Record<string, unknown> }>;
};

export type QuestionTypeDefinition = {
  id: QuestionType;
  label: string;
  category: "reading" | "listening" | "shared";
  BuilderEditor: ComponentType<EditorProps>;
  AnswerKeyEditor: ComponentType<EditorProps>;
  ExamRenderer: ComponentType<RendererProps>;
  ReviewRenderer: ComponentType<RendererProps>;
  responseSchema: z.ZodType;
  configSchema: z.ZodType;
  instruction: (group: InstructionGroup, context: InstructionContext) => QuestionInstruction;
  createDefault: (number: number) => QuestionGroupModel;
};

const optionSchema = z.object({ id: z.string().uuid(), label: z.string().min(1), text: z.string().min(1) });
const textQuestion = (number: number) => ({ id: crypto.randomUUID(), number, prompt: "Enter the answer.", config: { max_words: 2, max_numbers: 1 }, answer_key: { kind: "TEXT", accepted: ["sample answer"], case_sensitive: false }, order_index: 0 });
const newOptions = () => [{ id: crypto.randomUUID(), label: "A", text: "Option A" }, { id: crypto.randomUUID(), label: "B", text: "Option B" }, { id: crypto.randomUUID(), label: "C", text: "Option C" }];
const staticInstruction = (intro: string, options?: QuestionInstruction["options"]) => () => ({ intro, options });
const readingPassage = ({ passageNumber }: InstructionContext) => passageNumber ? `Reading Passage ${passageNumber}` : "the reading passage";

function limitInstruction(group: InstructionGroup): string {
  const limits = [...new Set(group.questions.map((question) => `${question.config.max_words ?? ""}:${question.config.max_numbers ?? ""}`))];
  if (limits.length !== 1) return "Use the word and/or number limit shown for each answer.";
  const [wordsText, numbersText] = limits[0].split(":");
  const words = wordsText ? Number(wordsText) : null;
  const numbers = numbersText ? Number(numbersText) : null;
  if (words && numbers) return `Choose NO MORE THAN ${words} WORDS AND/OR ${numbers} ${numbers === 1 ? "NUMBER" : "NUMBERS"} for each answer.`;
  if (words) return `Choose NO MORE THAN ${words} WORDS for each answer.`;
  if (numbers) return `Choose NO MORE THAN ${numbers} ${numbers === 1 ? "NUMBER" : "NUMBERS"} for each answer.`;
  return "Complete each answer using information from the source.";
}

const definitions: QuestionTypeDefinition[] = [
  {
    id: "multiple_choice", label: "Multiple Choice — Single", category: "shared",
    BuilderEditor: MultipleChoiceEditor, AnswerKeyEditor: MultipleChoiceEditor, ExamRenderer: MultipleChoiceRenderer, ReviewRenderer: MultipleChoiceRenderer,
    responseSchema: z.string(), configSchema: z.object({ options: z.array(optionSchema).min(2) }), instruction: staticInstruction("Choose the correct letter."),
    createDefault: (number) => { const options = newOptions().slice(0, 2); return { question_type: "multiple_choice", instruction: "", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Question prompt", config: { options }, answer_key: { kind: "SINGLE_OPTION", value: options[0].id }, order_index: 0 }] }; },
  },
  {
    id: "multiple_choice_multiple", label: "Multiple Choice — Multiple", category: "shared",
    BuilderEditor: MultipleChoiceMultipleEditor, AnswerKeyEditor: MultipleChoiceMultipleEditor, ExamRenderer: MultipleChoiceMultipleRenderer, ReviewRenderer: MultipleChoiceMultipleRenderer,
    responseSchema: z.array(z.string()), configSchema: z.object({}), instruction: staticInstruction("Choose the correct letters."),
    createDefault: (number) => { const options = newOptions(); return { question_type: "multiple_choice_multiple", instruction: "", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Question prompt", config: { options, min_selections: 2, max_selections: 2 }, answer_key: { kind: "MULTIPLE_OPTIONS", values: options.slice(0, 2).map((item) => item.id), order_matters: false }, order_index: 0 }] }; },
  },
  {
    id: "true_false_not_given", label: "True / False / Not Given", category: "reading",
    BuilderEditor: TrueFalseNotGivenEditor, AnswerKeyEditor: TrueFalseNotGivenEditor, ExamRenderer: TrueFalseNotGivenRenderer, ReviewRenderer: TrueFalseNotGivenRenderer,
    responseSchema: z.enum(["TRUE", "FALSE", "NOT_GIVEN"]), configSchema: z.object({}),
    instruction: (_group, context) => ({ intro: `Do the following statements agree with the information given in ${readingPassage(context)}?`, options: [
      { label: "TRUE", description: "if the statement agrees with the information" },
      { label: "FALSE", description: "if the statement contradicts the information" },
      { label: "NOT GIVEN", description: "if there is no information on this" },
    ] }),
    createDefault: (number) => ({ question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Statement", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, order_index: 0 }] }),
  },
  {
    id: "yes_no_not_given", label: "Yes / No / Not Given", category: "reading",
    BuilderEditor: YesNoNotGivenEditor, AnswerKeyEditor: YesNoNotGivenEditor, ExamRenderer: YesNoNotGivenRenderer, ReviewRenderer: YesNoNotGivenRenderer,
    responseSchema: z.enum(["YES", "NO", "NOT_GIVEN"]), configSchema: z.object({}),
    instruction: (_group, context) => ({ intro: `Do the following statements agree with the views/claims of the writer in ${readingPassage(context)}?`, options: [
      { label: "YES", description: "if the statement agrees with the views/claims of the writer" },
      { label: "NO", description: "if the statement contradicts the views/claims of the writer" },
      { label: "NOT GIVEN", description: "if it is impossible to say what the writer thinks about this" },
    ] }),
    createDefault: (number) => ({ question_type: "yes_no_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Statement", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "YES" }, order_index: 0 }] }),
  },
  {
    id: "text_completion", label: "Text Completion", category: "shared",
    BuilderEditor: TextCompletionEditor, AnswerKeyEditor: TextCompletionEditor, ExamRenderer: TextCompletionRenderer, ReviewRenderer: TextCompletionRenderer,
    responseSchema: z.string(), configSchema: z.object({}), instruction: (group) => ({ intro: `Complete the text below. ${limitInstruction(group)}` }),
    createDefault: (number) => ({ question_type: "text_completion", instruction: "", config: {}, order_index: 0, questions: [textQuestion(number)] }),
  },
  {
    id: "matching_headings", label: "Matching Headings", category: "reading",
    BuilderEditor: MatchingHeadingsEditor, AnswerKeyEditor: MatchingHeadingsEditor, ExamRenderer: MatchingHeadingsRenderer, ReviewRenderer: MatchingHeadingsRenderer,
    responseSchema: z.string(), configSchema: z.object({}), instruction: staticInstruction("Choose the correct heading for each paragraph from the list of headings below."),
    createDefault: (number) => { const options = [{ id: crypto.randomUUID(), label: "i", text: "First heading" }, { id: crypto.randomUUID(), label: "ii", text: "Second heading" }]; return { question_type: "matching_headings", instruction: "", config: { options, allow_option_reuse: false }, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Choose a heading.", config: { target_block_id: "" }, answer_key: { kind: "SINGLE_OPTION", value: options[0].id }, order_index: 0 }] }; },
  },
  {
    id: "matching", label: "Matching", category: "shared",
    BuilderEditor: MatchingEditor, AnswerKeyEditor: MatchingEditor, ExamRenderer: MatchingRenderer, ReviewRenderer: MatchingRenderer,
    responseSchema: z.string(), configSchema: z.object({}), instruction: staticInstruction("Match each prompt with the correct option."),
    createDefault: (number) => { const options = newOptions(); return { question_type: "matching", instruction: "", config: { options }, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Item to match", config: {}, answer_key: { kind: "SINGLE_OPTION", value: options[0].id }, order_index: 0 }] }; },
  },
];

for (const [id, label] of [["plan_labelling", "Plan Labelling"], ["map_labelling", "Map Labelling"], ["diagram_labelling", "Diagram Labelling"]] as const) {
  definitions.push({
    id, label, category: "listening", BuilderEditor: VisualLabellingEditor, AnswerKeyEditor: VisualLabellingEditor, ExamRenderer: VisualLabellingRenderer, ReviewRenderer: VisualLabellingRenderer,
    responseSchema: z.string(), configSchema: z.object({}), instruction: staticInstruction(`Label the ${label.split(" ")[0].toLowerCase()} using the options provided.`),
    createDefault: (number) => { const options = newOptions(); const questionId = crypto.randomUUID(); return { question_type: id, instruction: "", config: { options, markers: [{ id: crypto.randomUUID(), question_id: questionId, x: 0.5, y: 0.5 }] }, order_index: 0, questions: [{ id: questionId, number, prompt: "Choose the correct label.", config: {}, answer_key: { kind: "SINGLE_OPTION", value: options[0].id }, order_index: 0 }] }; },
  });
}

for (const [id, label, kind] of [["form_completion", "Form Completion", "FORM"], ["note_completion", "Note Completion", "NOTE"], ["table_completion", "Table Completion", "TABLE"], ["flow_chart_completion", "Flow-chart Completion", "FLOW_CHART"], ["summary_completion", "Summary Completion", "SUMMARY"], ["sentence_completion", "Sentence Completion", "SENTENCE"]] as const) {
  definitions.push({
    id, label, category: "listening", BuilderEditor: StructuredCompletionEditor, AnswerKeyEditor: StructuredCompletionEditor, ExamRenderer: StructuredCompletionRenderer, ReviewRenderer: StructuredCompletionRenderer,
    responseSchema: z.string(), configSchema: z.object({}), instruction: (group) => ({ intro: `Complete the ${label.replace(" Completion", "").toLowerCase()} below. ${limitInstruction(group)}` }),
    createDefault: (number) => { const question = textQuestion(number); const gap = { id: crypto.randomUUID(), type: "GAP" as const, text: "", question_id: question.id }; const layout = kind === "TABLE" ? { kind, columns: [{ id: crypto.randomUUID(), label: "Item" }, { id: crypto.randomUUID(), label: "Answer" }], rows: [{ id: crypto.randomUUID(), cells: [{ id: crypto.randomUUID(), type: "TEXT" as const, text: "Label" }, gap] }], nodes: [] } : { kind, columns: [], rows: [], nodes: [{ id: crypto.randomUUID(), type: "TEXT" as const, text: "Context", level: 0 }, { ...gap, level: 0 }] }; return { question_type: id, instruction: "", config: { layout }, order_index: 0, questions: [question] }; },
  });
}

definitions.push({
  id: "short_answer", label: "Short Answer", category: "listening", BuilderEditor: TextCompletionEditor, AnswerKeyEditor: TextCompletionEditor, ExamRenderer: TextCompletionRenderer, ReviewRenderer: TextCompletionRenderer,
  responseSchema: z.string(), configSchema: z.object({}), instruction: (group) => ({ intro: `Answer the questions below. ${limitInstruction(group)}` }),
  createDefault: (number) => ({ question_type: "short_answer", instruction: "", config: {}, order_index: 0, questions: [textQuestion(number)] }),
});

export const questionRegistry = Object.fromEntries(definitions.map((item) => [item.id, item])) as Record<QuestionType, QuestionTypeDefinition>;
export const questionTypeOptions = definitions.map(({ id, label }) => ({ id, label }));
export const readingQuestionTypeOptions = definitions.filter((item) => item.category !== "listening").map(({ id, label }) => ({ id, label }));
export const listeningQuestionTypeOptions = definitions.filter((item) => item.category !== "reading").map(({ id, label }) => ({ id, label }));
