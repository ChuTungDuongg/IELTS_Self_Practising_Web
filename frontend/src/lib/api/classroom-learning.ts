import { z } from "zod";
import { apiRequest } from "./client";
import { gradeSchema, lmsPath, queryString } from "./classroom-lms";

const id = z.string().uuid(), count = z.number().int().nonnegative(), metric = z.number().nullable();
export const skills = ["READING", "LISTENING", "WRITING", "SPEAKING"] as const;
const skill = z.enum(skills);
export const goalsSchema = z.object({ overall: metric, reading: metric, listening: metric, writing: metric, speaking: metric });
// Pydantic serializes Decimal planning targets as strings; keep that wire conversion here.
const wireGoals = z.object(Object.fromEntries(["overall", ...skills.map(s => s.toLowerCase())].map(k => [k, z.union([z.string(), z.number()]).nullable()])))
  .transform(value => goalsSchema.parse(Object.fromEntries(Object.entries(value).map(([key, band]) => [key, band === null ? null : Number(band)]))));
export const planSchema = z.object({ id, student_id: id, created_by_user_id: id, updated_by_user_id: id, title: z.string(), target_skill: skill, focus_area: z.string(), description: z.string().nullable(), status: z.enum(["ACTIVE", "COMPLETED", "ARCHIVED"]), revision: count, created_at: z.string(), updated_at: z.string(), completed_items: count, items: z.array(z.object({ id, assignment_id: id.nullable(), resource_id: id.nullable(), title: z.string(), available: z.boolean(), completed: z.boolean(), completion_source: z.enum(["ACCEPTED_ASSIGNMENT", "RESOURCE_MARKER", "NONE"]), completed_at: z.string().nullable() })) });
export const dashboardSchema = z.object({ start: z.string(), end: z.string(), active_students: count, assigned_activities: count, eligible_requirements: count, completion_rate: metric, on_time_rate: metric, counts: z.record(z.string(), count), pending_human: count, goals: wireGoals.nullable(),
  skills: z.array(z.object({ skill, sample_size: count, independent_assessments: count, recent_independent_assessments: count, latest: metric, average: metric, recent_average: metric, trends: z.array(z.object({ attempt_id: id, assignment_id: id, at: z.string(), band: z.number() })) })),
  question_types: z.array(z.object({ skill, category: z.string(), questions_attempted: count, questions_correct: count, unanswered: count, sample_size: count, repeated_exposures: count, accuracy: metric, recent_accuracy: metric, historical_accuracy: metric, recent_sample_size: count, trend: metric, confidence_level: z.enum(["INSUFFICIENT", "MEDIUM", "HIGH"]) })),
  criteria: z.array(z.object({ skill, context: z.string(), criterion: z.string(), sample_size: count, recent_sample_size: count, average: z.number(), recent_average: metric, historical_average: metric, trend: metric })),
  weaknesses: z.array(z.object({ weakness_type: z.enum(["QUESTION_TYPE", "CRITERION", "SKILL_BAND"]), skill, category: z.string(), evidence: z.string(), sample_size: count, severity: z.enum(["MODERATE", "HIGH"]), confidence_level: z.enum(["MEDIUM", "HIGH"]), recommendation_reason: z.string(), observed: z.number(), baseline: z.number() })),
  recent_assessments: z.array(gradeSchema), completion_by_assignment: z.array(z.object({ assignment_id: id, title: z.string(), counts: z.record(z.string(), count) })), total_completion_activities: count, attention_students: z.array(z.object({ student_id: id, display_name: z.string(), missing: count, pending_human: count })), recommendations: z.array(z.object({ assignment_id: id, title: z.string(), skill, category: z.string(), reason: z.string(), href: z.string() })), criteria_truncated: z.boolean(),
});
export type LearningDashboard = z.infer<typeof dashboardSchema>;
export type LearningGoals = z.infer<typeof goalsSchema>;
export type LearningPlan = z.infer<typeof planSchema>;
export type PlanWrite = Pick<LearningPlan, "title" | "target_skill" | "focus_area" | "description" | "status"> & { items: { assignment_id?: string; resource_id?: string }[]; expected_revision?: number };
export type LearningRange = { start?: string; end?: string; completion_offset?: number };
export async function getLearningDashboard(room: string, own: boolean, range: LearningRange, studentId?: string, signal?: AbortSignal) {
  const path = own ? "my-progress" : studentId ? `students/${encodeURIComponent(studentId)}/analytics` : "analytics";
  return dashboardSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/${path}?${queryString(range)}`, { signal }));
}
export async function saveLearningGoals(goals: LearningGoals) { return wireGoals.parse(await apiRequest<unknown>("/me/learning-goals", { method: "PUT", body: JSON.stringify(goals) })); }
export async function getLearningPlans(room: string, studentId?: string, offset = 0, signal?: AbortSignal) { return z.object({ items: z.array(planSchema), total: count }).parse(await apiRequest<unknown>(`${lmsPath(room)}/learning-plans?${queryString({ student_id: studentId, offset })}`, { signal })); }
export async function saveLearningPlan(room: string, student: string, input: PlanWrite, planId?: string) { return planSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/students/${encodeURIComponent(student)}/learning-plans${planId ? `/${encodeURIComponent(planId)}` : ""}`, { method: planId ? "PUT" : "POST", body: JSON.stringify(input) })); }
export async function completePlanResource(room: string, plan: string, item: string) { return planSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/learning-plans/${plan}/items/${item}/complete-resource`, { method: "POST" })); }
