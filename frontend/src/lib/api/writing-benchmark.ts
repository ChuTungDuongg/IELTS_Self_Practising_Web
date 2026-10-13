import { z } from "zod";
import { taskOneTypes } from "@/features/writing/task-types";
import { API_BASE_URL, ApiError, apiRequest, apiResponse, type ApiRequester } from "./client";

const root = "/admin/writing-benchmark";
const band = z.number().min(0).max(9).multipleOf(0.5);
const nullableBand = band.nullable();
const scoreRest = { cc: nullableBand, lr: nullableBand, gra: nullableBand };
const humanScores = z.union([z.object({ ta: nullableBand, ...scoreRest }).strict(), z.object({ tr: nullableBand, ...scoreRest }).strict()]);
export const benchmarkTaskTypes = taskOneTypes.map(([id]) => id);
const taskType = z.enum(benchmarkTaskTypes);

const listObject = z.object({ id: z.string().uuid(), code: z.string().regex(/^T[12]-\d{3}$/),
  task_number: z.union([z.literal(1), z.literal(2)]), sequence_number: z.number().int().min(1).max(100),
  status: z.enum(["DRAFT", "COMPLETE"]), split: z.enum(["DEV", "HOLDOUT"]),
  human_scores: humanScores, human_overall: nullableBand, has_image: z.boolean(), revision: z.number().int().nonnegative(),
  created_at: z.string(), updated_at: z.string(),
}).strict();

function taskSemantics(value: z.infer<typeof listObject>, context: z.RefinementCtx) {
  if ((value.task_number === 1) !== ("ta" in value.human_scores)) context.addIssue({ code: "custom", path: ["human_scores"], message: "Criterion does not match task." });
}

export const benchmarkSampleListSchema = listObject.superRefine(taskSemantics);
export const benchmarkSampleSchema = listObject.extend({ prompt: z.string().max(20000), essay: z.string().max(100000), task1_task_type: taskType.nullable(), source_note: z.string().max(2000).nullable(), redistributable: z.boolean() }).strict().superRefine(taskSemantics);
export const benchmarkSamplePatchSchema = z.object({
  expected_revision: z.number().int().nonnegative(), prompt: z.string().max(20000).optional(), essay: z.string().max(100000).optional(),
  split: z.enum(["DEV", "HOLDOUT"]).optional(), task1_task_type: taskType.nullable().optional(), source_note: z.string().max(2000).nullable().optional(), redistributable: z.boolean().optional(),
  human_scores: z.object({ ta: nullableBand.optional(), tr: nullableBand.optional(), cc: nullableBand.optional(), lr: nullableBand.optional(), gra: nullableBand.optional() }).strict().refine(value => !("ta" in value && "tr" in value), "Use the task-specific criterion.").optional(),
}).strict();

const splitCounts = z.object({ DEV: z.number().int().min(0).max(100), HOLDOUT: z.number().int().min(0).max(100) }).strict();
export const benchmarkTaskSummarySchema = z.object({ task_number: z.union([z.literal(1), z.literal(2)]), capacity: z.literal(100), total: z.number().int().min(0).max(100), draft: z.number().int().min(0).max(100), complete: z.number().int().min(0).max(100), split_counts: splitCounts, split_targets: splitCounts, overall_distribution: z.array(z.object({ band, actual: z.number().int().min(0).max(100), suggested: z.number().int().nonnegative().nullable() }).strict()).length(19) }).strict();
export const benchmarkSummarySchema = z.object({ tasks: z.array(benchmarkTaskSummarySchema).length(2) }).strict();
export const benchmarkCompletionIssueSchema = z.object({ path: z.string(), message: z.string() });

export type BenchmarkSample = z.infer<typeof benchmarkSampleSchema>;
export type BenchmarkListItem = z.infer<typeof benchmarkSampleListSchema>;
export type BenchmarkPatch = z.infer<typeof benchmarkSamplePatchSchema>;
export type BenchmarkSummary = z.infer<typeof benchmarkSummarySchema>;
export type BenchmarkTaskSummary = z.infer<typeof benchmarkTaskSummarySchema>;
export type BenchmarkTaskNumber = 1 | 2;
export type BenchmarkFieldIssue = z.infer<typeof benchmarkCompletionIssueSchema>;

const samplePath = (id: string) => `${root}/samples/${encodeURIComponent(id)}`;

export async function getWritingBenchmarkSummary(request: ApiRequester = apiRequest) {
  return benchmarkSummarySchema.parse(await request<unknown>(`${root}/summary`));
}
export async function listWritingBenchmarkSamples(task: BenchmarkTaskNumber, request: ApiRequester = apiRequest) {
  return z.array(benchmarkSampleListSchema).max(100).parse(await request<unknown>(`${root}/samples?task=${task}`));
}
export async function getWritingBenchmarkSample(id: string, request: ApiRequester = apiRequest) {
  return benchmarkSampleSchema.parse(await request<unknown>(samplePath(id)));
}
export async function createWritingBenchmarkSample(task: BenchmarkTaskNumber, request: ApiRequester = apiRequest) {
  return benchmarkSampleSchema.parse(await request<unknown>(`${root}/samples`, { method: "POST", body: JSON.stringify({ task_number: task }) }));
}
export async function updateWritingBenchmarkSample(id: string, patch: BenchmarkPatch, request: ApiRequester = apiRequest) {
  return benchmarkSampleSchema.parse(await request<unknown>(samplePath(id), { method: "PATCH", body: JSON.stringify(benchmarkSamplePatchSchema.parse(patch)) }));
}
export async function completeWritingBenchmarkSample(id: string, revision: number, request: ApiRequester = apiRequest) {
  return benchmarkSampleSchema.parse(await request<unknown>(`${samplePath(id)}/complete`, { method: "POST", body: JSON.stringify({ expected_revision: revision }) }));
}
export async function deleteWritingBenchmarkSample(id: string, revision: number, request: ApiRequester = apiRequest) {
  await request<unknown>(`${samplePath(id)}?expected_revision=${revision}`, { method: "DELETE" });
}
export async function uploadWritingBenchmarkImage(id: string, file: File, revision: number, request: ApiRequester = apiRequest) {
  const body = new FormData(); body.set("file", file); body.set("expected_revision", String(revision));
  return benchmarkSampleSchema.parse(await request<unknown>(`${samplePath(id)}/image`, { method: "POST", body }));
}
export async function removeWritingBenchmarkImage(id: string, revision: number, request: ApiRequester = apiRequest) {
  return benchmarkSampleSchema.parse(await request<unknown>(`${samplePath(id)}/image?expected_revision=${revision}`, { method: "DELETE" }));
}
export function writingBenchmarkImageUrl(id: string, revision: number) {
  return `${API_BASE_URL}${samplePath(id)}/image?revision=${revision}`;
}
export async function exportWritingBenchmarkBundle(request: typeof apiResponse = apiResponse) {
  const response = await request(`${root}/export`);
  return { blob: await response.blob(), filename: "writing-benchmark.zip" };
}
export function benchmarkCompletionIssues(error: unknown): BenchmarkFieldIssue[] {
  if (!(error instanceof ApiError) || error.code !== "BENCHMARK_INCOMPLETE") return [];
  const parsed = z.object({ errors: z.array(benchmarkCompletionIssueSchema) }).safeParse(error.details);
  return parsed.success ? parsed.data.errors : [];
}
