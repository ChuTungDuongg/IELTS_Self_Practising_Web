import type { ComponentType } from "react";
import { z } from "zod";
import {
  MatchingHeadingsEditor,
  MultipleChoiceEditor,
  TextCompletionEditor,
  TrueFalseNotGivenEditor,
  type EditorProps,
} from "./editors";
import {
  MatchingHeadingsRenderer,
  MultipleChoiceRenderer,
  TextCompletionRenderer,
  TrueFalseNotGivenRenderer,
  type RendererProps,
} from "./renderers";
import type { QuestionGroupModel, QuestionType } from "./types";

const optionSchema = z.object({ id: z.string().uuid(), label: z.string().min(1), text: z.string().min(1) });
const choiceKeySchema = z.object({ kind: z.literal("SINGLE_OPTION"), value: z.string().min(1) });
const textKeySchema = z.object({ type: z.literal("text"), accepted: z.array(z.string()).min(1), case_sensitive: z.boolean() });

export type QuestionTypeDefinition = {
  id: QuestionType;
  label: string;
  category: "reading" | "shared";
  BuilderEditor: ComponentType<EditorProps>;
  AnswerKeyEditor: ComponentType<EditorProps>;
  ExamRenderer: ComponentType<RendererProps>;
  ReviewRenderer: ComponentType<RendererProps>;
  responseSchema: z.ZodType;
  configSchema: z.ZodType;
  createDefault: (number: number) => QuestionGroupModel;
};

const definitions: QuestionTypeDefinition[] = [
  {
    id: "multiple_choice", label: "Multiple Choice — Single", category: "shared",
    BuilderEditor: MultipleChoiceEditor, AnswerKeyEditor: MultipleChoiceEditor,
    ExamRenderer: MultipleChoiceRenderer, ReviewRenderer: MultipleChoiceRenderer,
    responseSchema: z.string(), configSchema: z.object({ options: z.array(optionSchema).min(2) }),
    createDefault: (number) => {
      const first = crypto.randomUUID();
      const second = crypto.randomUUID();
      return { question_type: "multiple_choice", instruction: "Choose the correct answer.", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Question prompt", config: { options: [{ id: first, label: "A", text: "Option A" }, { id: second, label: "B", text: "Option B" }] }, answer_key: choiceKeySchema.parse({ kind: "SINGLE_OPTION", value: first }), order_index: 0 }] };
    },
  },
  {
    id: "true_false_not_given", label: "True / False / Not Given", category: "reading",
    BuilderEditor: TrueFalseNotGivenEditor, AnswerKeyEditor: TrueFalseNotGivenEditor,
    ExamRenderer: TrueFalseNotGivenRenderer, ReviewRenderer: TrueFalseNotGivenRenderer,
    responseSchema: z.enum(["TRUE", "FALSE", "NOT_GIVEN"]), configSchema: z.object({}),
    createDefault: (number) => ({ question_type: "true_false_not_given", instruction: "Do the statements agree with the information in the passage?", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Statement", config: {}, answer_key: choiceKeySchema.parse({ kind: "SINGLE_OPTION", value: "TRUE" }), order_index: 0 }] }),
  },
  {
    id: "text_completion", label: "Text Completion", category: "shared",
    BuilderEditor: TextCompletionEditor, AnswerKeyEditor: TextCompletionEditor,
    ExamRenderer: TextCompletionRenderer, ReviewRenderer: TextCompletionRenderer,
    responseSchema: z.string(), configSchema: z.object({ max_words: z.number().nullable().optional(), max_numbers: z.number().nullable().optional() }),
    createDefault: (number) => ({ question_type: "text_completion", instruction: "Complete the sentence using words from the passage.", config: {}, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Complete this sentence: ____", config: { max_words: 2, max_numbers: 1 }, answer_key: textKeySchema.parse({ type: "text", accepted: ["sample answer"], case_sensitive: false }), order_index: 0 }] }),
  },
  {
    id: "matching_headings", label: "Matching Headings", category: "reading",
    BuilderEditor: MatchingHeadingsEditor, AnswerKeyEditor: MatchingHeadingsEditor,
    ExamRenderer: MatchingHeadingsRenderer, ReviewRenderer: MatchingHeadingsRenderer,
    responseSchema: z.string(), configSchema: z.object({ target_block_id: z.string().uuid() }),
    createDefault: (number) => {
      const first = crypto.randomUUID();
      const second = crypto.randomUUID();
      return { question_type: "matching_headings", instruction: "Choose the correct heading for each paragraph.", config: { options: [{ id: first, label: "i", text: "First heading" }, { id: second, label: "ii", text: "Second heading" }], allow_option_reuse: false }, order_index: 0, questions: [{ id: crypto.randomUUID(), number, prompt: "Choose a heading for the selected paragraph.", config: { target_block_id: "" }, answer_key: choiceKeySchema.parse({ kind: "SINGLE_OPTION", value: first }), order_index: 0 }] };
    },
  },
];

export const questionRegistry = Object.fromEntries(definitions.map((item) => [item.id, item])) as Record<QuestionType, QuestionTypeDefinition>;
export const questionTypeOptions = definitions.map(({ id, label }) => ({ id, label }));
