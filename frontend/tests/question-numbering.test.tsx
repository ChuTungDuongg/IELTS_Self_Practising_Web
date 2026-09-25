import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { completedQuestionSlots, groupQuestionRange, questionNumbers } from "@/features/questions/numbering";
import { MultipleChoiceMultipleRenderer } from "@/features/questions/renderers";
import type { ExamGroup } from "@/features/questions/types";

function multi(start: number, count: number): ExamGroup {
  const options = Array.from({ length: count + 2 }, (_, index) => ({ id: String(index), label: String.fromCharCode(65 + index), text: `Fictional option ${index}` }));
  return {
    id: `group-${start}`,
    question_type: "multiple_choice_multiple",
    instruction: `Choose ${count}`,
    config: {},
    order_index: 0,
    questions: [{ id: `question-${start}`, number: start, prompt: "Select fictional options", config: { options, min_selections: count, max_selections: count }, order_index: 0 }],
  };
}

describe("numbered multi select groups", () => {
  it("counts a single MCQ once and a shared two or three choice group by its required selections", () => {
    expect(groupQuestionRange({ question_type: "multiple_choice", questions: [{ number: 21, config: {} }] })).toBe("Q21");
    expect(questionNumbers({ question_type: "multiple_choice", questions: [{ number: 21, config: {} }] })).toEqual([21]);
    expect(groupQuestionRange(multi(13, 2))).toBe("Q13–14");
    expect(questionNumbers(multi(21, 3))).toEqual([21, 22, 23]);
    expect(questionNumbers(multi(13, 2)).at(-1)! + 1).toBe(15);
  });

  it("fills two progress slots only after two distinct responses", () => {
    const config = multi(13, 2).questions[0].config;
    expect(completedQuestionSlots("multiple_choice_multiple", config, [])).toBe(0);
    expect(completedQuestionSlots("multiple_choice_multiple", config, ["0"])).toBe(1);
    expect(completedQuestionSlots("multiple_choice_multiple", config, ["0", "1"])).toBe(2);
    expect(completedQuestionSlots("multiple_choice_multiple", config, ["0", "0"])).toBe(1);
  });

  it("renders one shared stem and prevents a third selection", () => {
    const group = multi(13, 2);
    const onAnswer = vi.fn();
    const { rerender } = render(<MultipleChoiceMultipleRenderer group={group} values={{}} onAnswer={onAnswer} />);
    expect(screen.getAllByText("Select fictional options")).toHaveLength(1);
    expect(screen.getByText("13–14")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /A\. Fictional option 0/ }));
    expect(onAnswer).toHaveBeenCalledWith("question-13", ["0"]);
    rerender(<MultipleChoiceMultipleRenderer group={group} values={{ "question-13": ["0", "1"] }} onAnswer={onAnswer} />);
    expect(screen.getByRole("checkbox", { name: /C\. Fictional option 2/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /A\. Fictional option 0/ })).not.toBeDisabled();
  });
});
