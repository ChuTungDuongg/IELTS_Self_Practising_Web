import { z } from "zod";
import { apiRequest, API_BASE_URL } from "./client";

const root = "/admin/speaking-benchmark";
const record = z.record(z.string(), z.unknown());
const post = (body?: unknown) => ({ method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
export const labelSelectionSchema = z.object({ kind: z.enum(["LEGACY", "INDEPENDENT", "ADJUDICATED"]), id: z.string().uuid().nullable().optional(), revision: z.number().int().positive().nullable().optional() }).strict();
export type LabelSelection = z.infer<typeof labelSelectionSchema>;
export const qualityPolicySchema = z.object({ protocol: z.literal("speaking-dataset-quality-v1").default("speaking-dataset-quality-v1"), require_human_label: z.boolean().default(true), require_adjudication: z.boolean().default(false), require_source_bound_labels: z.boolean().default(true), require_asr_references: z.boolean().default(false), require_all_parts: z.boolean().default(true), minimum_independent_candidates: z.number().int().min(1).max(10000).default(10) });
export type QualityPolicy = z.infer<typeof qualityPolicySchema>;
export type QualityRequest = { cohort: { sample_id: string; review_revision: number }[]; label_selection: LabelSelection; policy: QualityPolicy };
export const qualityReportSchema = z.object({ protocol: z.string(), evaluated_at: z.string(), status: z.enum(["READY", "NEEDS_REVIEW", "BLOCKED", "INSUFFICIENT_DATA"]), issues: z.array(z.object({ code: z.string(), severity: z.enum(["BLOCKED", "NEEDS_REVIEW", "INSUFFICIENT_DATA"]), artifact: z.string(), artifact_id: z.string(), remediation: z.string() })), samples: z.array(record), issue_counts: z.record(z.string(), z.number()), eligible_samples: z.number(), ineligible_samples: z.number(), independent_candidates: z.number(), fingerprint: z.string() });
export type QualityReport = z.infer<typeof qualityReportSchema>;
export const suiteSchema = z.object({ id: z.string(), family_id: z.string(), revision: z.number(), name: z.string(), description: z.string(), configuration: record, fingerprint: z.string(), frozen_at: z.string(), created_at: z.string() });
export type EvaluationSuite = z.infer<typeof suiteSchema>;
export const persistedSelectionSchema = z.discriminatedUnion("kind", [z.object({ kind: z.literal("EXPERIMENT"), id: z.string().uuid(), variant_key: z.string().min(1).max(80), configuration_fingerprint: z.null().optional() }).strict(), z.object({ kind: z.literal("GRADING"), configuration_fingerprint: z.string().regex(/^[a-f0-9]{64}$/), id: z.null().optional(), variant_key: z.null().optional() }).strict()]);
export type PersistedSelection = z.infer<typeof persistedSelectionSchema>;
export const metrics = ["wer", "cer", "filler_recall", "repetition_recall", "recognition_coverage", "failure_rate", "latency_ms", "real_time_factor", "overall_mae", "fc_mae", "lr_mae", "gra_mae", "pr_mae", "exact_agreement", "within_0_5", "signed_bias_abs", "score_coverage", "missing_overall_rate", "unknown_billing_attempts", "provider_audio_ms", "physical_requests", "cache_reuse_rate", "missing_artifact_count"] as const;
export const gatePolicySchema = z.object({ protocol: z.literal("speaking-regression-gate-v1").default("speaking-regression-gate-v1"), comparison: z.enum(["CONFIGURATION", "LEXICAL_ASR"]).default("CONFIGURATION"), minimum_independent_candidates: z.number().int().min(1).max(10000).default(10), minimum_prediction_coverage: z.number().positive().max(1).default(1), minimum_reference_coverage: z.number().positive().max(1).default(1), thresholds: z.array(z.object({ metric: z.enum(metrics), max_regression: z.number().finite().nonnegative() })).min(1).max(30), max_unknown_billing_attempts: z.number().int().nonnegative().max(10000).default(0) }).refine(value => new Set(value.thresholds.map(row => row.metric)).size === value.thresholds.length, "Each metric requires one threshold");
export type GatePolicy = z.infer<typeof gatePolicySchema>;
export const gateSchema = z.object({ id: z.string(), name: z.string(), suite_id: z.string(), baseline: persistedSelectionSchema, candidate: persistedSelectionSchema, policy: gatePolicySchema, fingerprint: z.string(), created_at: z.string() });
export type RegressionGate = z.infer<typeof gateSchema>;
export const regressionReportSchema = z.object({ id: z.string(), gate_id: z.string(), status: z.enum(["PASS", "FAIL", "INCONCLUSIVE", "INVALID"]), protocol: z.string(), fingerprint: z.string(), report: record, created_at: z.string() });
export type RegressionReport = z.infer<typeof regressionReportSchema>;
// Snapshots retain the complete read-only report and the frozen inputs.
export const snapshotSchema = z.object({ id: z.string(), fingerprint: z.string(), created_at: z.string() }).passthrough();
export type QualitySnapshot = z.infer<typeof snapshotSchema>;
export async function evaluateQuality(body: QualityRequest) { return qualityReportSchema.parse(await apiRequest(`${root}/quality`, post(body))); }
export async function saveQualitySnapshot(body: QualityRequest) { return snapshotSchema.parse(await apiRequest(`${root}/quality/snapshots`, post(body))); }
export async function qualitySnapshots(offset = 0) { return z.array(snapshotSchema).parse(await apiRequest(`${root}/quality/snapshots?offset=${offset}&limit=25`)); }
export async function qualitySnapshot(id: string) { return snapshotSchema.parse(await apiRequest(`${root}/quality/snapshots/${encodeURIComponent(id)}`)); }
export async function listSuites(offset = 0) { return z.array(suiteSchema).parse(await apiRequest(`${root}/evaluation-suites?offset=${offset}&limit=25`)); }
export async function createSuite(body: QualityRequest & { name: string; description: string; family_id?: string; expected_revision: number; holdout_evaluation: boolean }) { return suiteSchema.parse(await apiRequest(`${root}/evaluation-suites`, post(body))); }
export async function getSuite(id: string, holdout = false) { return suiteSchema.parse(await apiRequest(`${root}/evaluation-suites/${encodeURIComponent(id)}?holdout_evaluation=${holdout}`)); }
export async function suiteAudits(id: string) { return z.array(record).parse(await apiRequest(`${root}/evaluation-suites/${encodeURIComponent(id)}/audits`)); }
export async function listGates(offset = 0) { return z.array(gateSchema).parse(await apiRequest(`${root}/regression-gates?offset=${offset}&limit=25`)); }
export async function createGate(body: { name: string; suite_id: string; baseline: PersistedSelection; candidate: PersistedSelection; policy: GatePolicy }) { return gateSchema.parse(await apiRequest(`${root}/regression-gates`, post(body))); }
export async function getGate(id: string) { return gateSchema.parse(await apiRequest(`${root}/regression-gates/${encodeURIComponent(id)}`)); }
export async function evaluateGate(id: string, holdout = false) { return regressionReportSchema.parse(await apiRequest(`${root}/regression-gates/${encodeURIComponent(id)}/evaluate`, post({ holdout_evaluation: holdout }))); }
export async function gateReports(id: string) { return z.array(regressionReportSchema).parse(await apiRequest(`${root}/regression-gates/${encodeURIComponent(id)}/reports?limit=25`)); }
export async function regressionReport(id: string) { return regressionReportSchema.parse(await apiRequest(`${root}/regression-reports/${encodeURIComponent(id)}`)); }
export const regressionExportUrl = (id: string, format: "csv" | "json") => `${API_BASE_URL}${root}/regression-reports/${encodeURIComponent(id)}/export.${format}`;
