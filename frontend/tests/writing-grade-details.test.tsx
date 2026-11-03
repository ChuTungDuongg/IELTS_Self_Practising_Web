import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { GradeDetails } from "@/features/classrooms/lms/gradebook";
import { gradeSchema } from "@/lib/api/classroom-lms";

it("uses the same focused Writing task band in grade details without a skill band", () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const score = gradeSchema.parse({
    assignment_id: id, root_id: id, kind: "ATTEMPT", result_attempt_id: id,
    skill: "WRITING", scope: "FOCUSED_UNIT", context: "CLASSROOM", band: null,
    raw_score: null, max_score: null, provenance: "HUMAN_FINAL", finished_at: "2026-11-03T00:00:00Z",
    accepted: true, late: false, submission_status: "SUBMITTED", mixed_context_fallback: false,
    breakdown: [{ attempt_id: id, skill: "WRITING", band: null, raw_score: null, max_score: null,
      provenance: "HUMAN_FINAL", task_score: 4.625 }],
  });
  render(<GradeDetails score={score} classroomId={id} />);
  expect(screen.getByText(/WRITING: Task: 4.5/)).toBeInTheDocument();
  expect(screen.queryByText(/4.625|4.63/)).not.toBeInTheDocument();
  expect(score.band).toBeNull();
});
