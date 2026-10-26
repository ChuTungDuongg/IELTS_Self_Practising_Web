import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import { completedQuestionSlots, questionNumbers } from "@/features/questions/numbering";
import type { ExamGroup, PassageBlock, QuestionGroupModel } from "@/features/questions/types";
import savedContracts from "../../backend/tests/fixtures/question-contracts.json";

type Contract = { group: QuestionGroupModel & { id: string }; passageBlocks: PassageBlock[]; response: string | string[]; score: number };
const contracts = savedContracts as unknown as Contract[];

describe("persisted question contracts shared with backend scoring tests", () => {
  it("retains every canonical identifier and all four registered components", () => {
    expect(contracts.map(({ group }) => group.question_type).sort()).toEqual(Object.keys(questionRegistry).sort());
    for (const definition of Object.values(questionRegistry)) {
      for (const component of [definition.BuilderEditor, definition.AnswerKeyEditor, definition.ExamRenderer, definition.ReviewRenderer]) expect(component).toBeTypeOf("function");
    }
  });

  it.each(contracts)("preserves $group.question_type serialization, identities, answers and numbering", ({ group, passageBlocks, response, score }) => {
    const saved = JSON.stringify(group);
    expect(JSON.parse(saved)).toEqual(group);
    const definition = questionRegistry[group.question_type];
    expect(definition.responseSchema.parse(response)).toEqual(response);
    expect(questionNumbers(group)).toEqual(Array.from({ length: score }, (_, index) => 11 + index));
    expect(completedQuestionSlots(group.question_type, group.questions[0].config, response)).toBe(score);
    const { answer_key: key, ...question } = group.questions[0];
    const candidate = { ...group, questions: [question] } as ExamGroup;
    const onAnswer = vi.fn();
    const Renderer = definition.ExamRenderer;
    const view = render(<Renderer group={candidate} passageBlocks={passageBlocks} values={{}} onAnswer={onAnswer} />);
    if (Array.isArray(response)) {
      const inputs = () => view.container.querySelectorAll<HTMLInputElement>("input[type=checkbox]");
      const options = question.config.options as Array<{ id: string }>;
      fireEvent.click(inputs()[options.findIndex(option => option.id === response[0])]);
      expect(onAnswer).toHaveBeenLastCalledWith(question.id, [response[0]]);
      view.rerender(<Renderer group={candidate} passageBlocks={passageBlocks} values={{ [question.id!]: [response[0]] }} onAnswer={onAnswer} />);
      fireEvent.click(inputs()[options.findIndex(option => option.id === response[1])]);
      expect(onAnswer).toHaveBeenLastCalledWith(question.id, response);
    } else if (view.container.querySelector("select")) {
      fireEvent.change(screen.getByRole("combobox"), { target: { value: response } });
      expect(onAnswer).toHaveBeenCalledWith(question.id, response);
    } else if (view.container.querySelector("input[type=radio]")) {
      const radio = Array.from(view.container.querySelectorAll<HTMLInputElement>("input[type=radio]"))[0];
      fireEvent.click(radio);
      expect(onAnswer).toHaveBeenCalledWith(question.id, response);
    } else {
      fireEvent.change(screen.getByRole("textbox"), { target: { value: response } });
      expect(onAnswer).toHaveBeenCalledWith(question.id, response);
    }
    expect(JSON.stringify(group)).toBe(saved);
    expect(key.kind).toBeTruthy();
    view.unmount();
    const Review = definition.ReviewRenderer;
    const reviewed = render(<Review group={candidate} passageBlocks={passageBlocks} values={{ [question.id!]: response }} disabled />);
    expect(reviewed.container.querySelectorAll("input, select").length).toBeGreaterThan(0);
    reviewed.container.querySelectorAll("input, select").forEach(control => expect(control).toBeDisabled());
  });
});
