import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { taskOneTypes, taskTwoTypes, writingTaskTypeSchema } from "@/features/writing/task-types";

const root = "/admin/writing-anchors";
const band = z.number().finite().min(0).max(9).multipleOf(0.5);
export const humanScoresSchema = z.object({ ta: band, cc: band, lr: band, gra: band }).strict();
export const anchorInputSchema = z.object({
  source_kind: z.enum(["BUILDER_TASK", "CUSTOM_TASK"]).default("BUILDER_TASK"),
  writing_task_id: z.string().uuid().nullable().optional(),
  task_number: z.union([z.literal(1), z.literal(2)]).nullable().optional(),
  custom_prompt: z.string().min(1).max(100000).nullable().optional(),
  custom_task_type: writingTaskTypeSchema.nullable().optional(),
  response_text: z.string().min(1).max(100000).refine(v => v.trim().length > 0),
  human_scores: humanScoresSchema, admin_note: z.string().max(2000).nullable().optional(), provenance: z.string().max(2000).nullable().optional(),
}).strict().superRefine((input, ctx) => {
  const valid = input.source_kind === "BUILDER_TASK"
    ? Boolean(input.writing_task_id) && input.task_number == null && input.custom_prompt == null && input.custom_task_type == null
    : input.writing_task_id == null && Boolean(input.task_number) && Boolean(input.custom_prompt?.trim()) && (!input.custom_task_type || (input.task_number === 1 ? taskOneTypes : taskTwoTypes).some(([id]) => id === input.custom_task_type));
  if (!valid) ctx.addIssue({ code: "custom", message: "Nguồn đề không hợp lệ hoặc thiếu đề bài." });
});
export type AnchorInput = z.infer<typeof anchorInputSchema>;
export const anchorSetSchema = z.object({ id: z.string().uuid(), name: z.string(), version: z.number().int(), status: z.enum(["DRAFT", "ACTIVE", "RETIRED"]), created_at: z.string(), activated_at: z.string().nullable(), retired_at: z.string().nullable() });
export type AnchorSet = z.infer<typeof anchorSetSchema>;
export const frozenTaskSchema = z.object({ id: z.string().uuid(), test_version_id: z.string().uuid(), test_title: z.string(), version_number: z.number().int(), task_number: z.union([z.literal(1), z.literal(2)]), task_type: z.string().nullable(), prompt_preview: z.string() });
export type FrozenTask = z.infer<typeof frozenTaskSchema>;
export const anchorTaskSchema = frozenTaskSchema.extend({ id: z.string().uuid().nullable(), test_version_id: z.string().uuid().nullable(), version_number: z.number().int().nullable() });
export type AnchorTask = z.infer<typeof anchorTaskSchema>;
export const anchorSummarySchema = z.object({ id: z.string().uuid(), anchor_set_id: z.string().uuid(), source_kind: z.enum(["BUILDER_TASK", "CUSTOM_TASK"]), task: anchorTaskSchema, word_count: z.number().int(), human_scores: humanScoresSchema, created_at: z.string() });
export const anchorDetailSchema = anchorSummarySchema.extend({ custom_prompt: z.string().nullable(), response_text: z.string(), admin_note: z.string().nullable(), provenance: z.string().nullable() });
export type AnchorDetail = z.infer<typeof anchorDetailSchema>;
const row = z.object({ criterion: z.enum(["ta", "cc", "lr", "gra"]), counts: z.record(z.string(), z.number().int()), ladder: z.array(z.number().int()), readiness: z.enum(["EMPTY", "PARTIAL", "PAIRWISE_USABLE", "RECOMMENDED_COVERAGE"]), pilot_complete: z.boolean() });
export const anchorCoverageSchema = z.object({ active_set: anchorSetSchema.nullable(), evaluated_set: anchorSetSchema.nullable().optional(), production_task1: z.array(row), research_task1_ta: z.array(row.extend({ source_id: z.string().uuid().optional(), task: anchorTaskSchema })), research_task2: z.array(row), recommendations: z.array(z.string()), node_budget: z.number().int() });
export type AnchorCoverage = z.infer<typeof anchorCoverageSchema>;
const bankStateSchema = z.object({ current: anchorSetSchema.nullable(), working: anchorSetSchema.nullable(), current_count: z.number().int(), working_count: z.number().int() });
export type AnchorBankState = z.infer<typeof bankStateSchema>;
const page = <T extends z.ZodType>(item: T) => z.object({ items: z.array(item), total: z.number().int(), offset: z.number().int(), limit: z.number().int() });
const anchorPage = page(anchorSummarySchema);
export type AnchorPage = z.infer<typeof anchorPage>;
const query = (filters: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v !== undefined && v !== "") params.set(k, String(v)); });
  return params.toString();
};
export async function listAnchorSets(api: ApiRequester = apiRequest) { return z.object({ items: z.array(anchorSetSchema) }).parse(await api(`${root}/sets`)); }
export async function createAnchorDraft(name = "Human Writing anchors", api: ApiRequester = apiRequest) { return anchorSetSchema.parse(await api(`${root}/sets`, { method: "POST", body: JSON.stringify({ name }) })); }
export async function activateAnchorSet(id: string, api: ApiRequester = apiRequest) { return anchorSetSchema.parse(await api(`${root}/sets/${id}/activate`, { method: "POST" })); }
export async function getAnchorCoverage(setId?: string, api: ApiRequester = apiRequest) { return anchorCoverageSchema.parse(await api(`${root}/coverage${setId ? `?set_id=${encodeURIComponent(setId)}` : ""}`)); }
export async function getAnchorBank(api: ApiRequester = apiRequest) { return bankStateSchema.parse(await api(`${root}/bank`)); }
export async function editAnchorBank(api: ApiRequester = apiRequest) { return anchorSetSchema.parse(await api(`${root}/bank/edit`, { method: "POST" })); }
export async function applyAnchorBank(id: string, api: ApiRequester = apiRequest) { return anchorSetSchema.parse(await api(`${root}/bank/${id}/apply`, { method: "POST" })); }
export async function cancelAnchorBank(id: string, api: ApiRequester = apiRequest) { await api(`${root}/bank/${id}/working`, { method: "DELETE" }); }
export async function deleteAnchorBank(id: string, api: ApiRequester = apiRequest) { await api(`${root}/bank/${id}/current`, { method: "DELETE" }); }
export async function getAnchorHistory(api: ApiRequester = apiRequest) { return z.object({ items: z.array(anchorSetSchema) }).parse(await api(`${root}/history`)); }
export async function listFrozenTasks(filters: { search?: string; task_number?: number; offset?: number; limit?: number } = {}, api: ApiRequester = apiRequest) { return page(frozenTaskSchema).parse(await api(`${root}/tasks?${query(filters)}`)); }
export async function listAnchors(filters: { set_id?: string; search?: string; task_number?: number; writing_task_id?: string; task_type?: string; status?: string; offset?: number } = {}, api: ApiRequester = apiRequest) { return anchorPage.parse(await api(`${root}/anchors?${query(filters)}`)); }
export async function getAnchor(id: string, api: ApiRequester = apiRequest) { return anchorDetailSchema.parse(await api(`${root}/anchors/${id}`)); }
export async function createAnchor(setId: string, input: AnchorInput, api: ApiRequester = apiRequest) { return anchorDetailSchema.parse(await api(`${root}/sets/${setId}/anchors`, { method: "POST", body: JSON.stringify(anchorInputSchema.parse(input)) })); }
export async function updateAnchor(id: string, input: AnchorInput, api: ApiRequester = apiRequest) { return anchorDetailSchema.parse(await api(`${root}/anchors/${id}`, { method: "PATCH", body: JSON.stringify(anchorInputSchema.parse(input)) })); }
export async function deleteAnchor(id: string, api: ApiRequester = apiRequest) { await api(`${root}/anchors/${id}`, { method: "DELETE" }); }
