import { z } from "zod";

export const gradingSchema = z.object({
  context: z.enum(["PERSONAL", "CLASSROOM"]),
  can_edit_final: z.boolean().default(false),
  can_copy_ai_to_final: z.boolean().default(false),
  waiting_for_teacher: z.boolean().default(false),
});
export type GradingCapability = z.infer<typeof gradingSchema>;
export type AssignmentGradingScope = { classroomId: string; assignmentId: string };
