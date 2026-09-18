import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";

describe("question registry", () => {
  it("creates a structured MCQ with an inline answer key", () => {
    const group = questionRegistry.multiple_choice.createDefault(7);
    expect(group.questions[0].number).toBe(7);
    expect(group.questions[0].config.options).toHaveLength(2);
    expect(group.questions[0].answer_key.accepted).toEqual(["A"]);
  });

  it("routes exam answers through the registered renderer", () => {
    const group = questionRegistry.true_false_not_given.createDefault(3) as ExamGroup;
    group.id = crypto.randomUUID();
    group.questions[0].id = crypto.randomUUID();
    const onAnswer = vi.fn();
    const Renderer = questionRegistry.true_false_not_given.ExamRenderer;
    render(<Renderer group={group} values={{}} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByLabelText("FALSE"));
    expect(onAnswer).toHaveBeenCalledWith(group.questions[0].id, "FALSE");
  });
});
