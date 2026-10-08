import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { aiCriterionSchema } from "@/lib/api/writing-ai";
import { CriterionAssessmentCard } from "@/features/writing/writing-ai-criterion-card";

it("renders an established band with unavailable feedback from an SSE payload", () => {
  const criterion = aiCriterionSchema.parse({ score: 7.5, feedback_status: "UNAVAILABLE", feedback_error_code: "AI_FEEDBACK_UNAVAILABLE", evidence: [], strengths: [], improvements: [] });
  render(<CriterionAssessmentCard trait="cc" taskNumber={1} assessment={criterion} />);
  expect(screen.getByText("Band 7.5")).toBeInTheDocument();
  expect(screen.getByText("Điểm đã được xác định. Nhận xét hiện chưa khả dụng.")).toBeInTheDocument();
  expect(aiCriterionSchema.safeParse({ ...criterion, feedback: "Fabricated", feedback_status: "UNAVAILABLE" }).success).toBe(false);
});
