import { z } from "zod";

const label = z.string().min(1).max(120);
const id = z.string().min(1).max(40);
const decimal = z.union([z.number(), z.string().regex(/^[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i).transform(Number)]).pipe(z.number().finite());
const numeric = decimal.pipe(z.number().min(-1e12).max(1e12));
const confidence = z.enum(["HIGH", "MEDIUM", "LOW", "UNUSABLE"]);
const common = { confidence, summary: z.string().max(600), uncertainty: z.array(z.string().max(240)).max(4) };
const entity = z.object({ id, label });
const edge = z.object({ source: id, target: id, label: z.string().max(120).nullable() });
const point = z.object({ category: label, value: numeric.nullable(), confidence: z.number().min(0).max(1), value_is_labelled: z.boolean().nullable().optional() });
const location = z.enum(["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "centre", "unspecified"]);
const component = z.object({
  id, kind: z.enum(["line_graph", "bar_chart", "pie_chart", "table"]), title: z.string().max(120),
  unit: z.string().max(80).nullable(), state: z.string().max(120).nullable(),
  x_axis: z.string().max(120).nullable(), y_axis: z.string().max(120).nullable(), ordered_categories: z.boolean(),
  categories: z.array(label).max(30), legend: z.array(label).max(12),
  series: z.array(z.object({ id, name: label, points: z.array(point).max(30) })).max(12),
  row_headers: z.array(label).max(30), column_headers: z.array(label).max(30),
  cells: z.array(z.object({ row: label, column: label, value: numeric.nullable(), label: z.string().max(120).nullable(), confidence: z.number().min(0).max(1) })).max(120),
});
export const visualReferenceSchema = z.discriminatedUnion("visual_family", [
  z.object({ ...common, visual_family: z.literal("chart_table"), components: z.array(component).min(1).max(4) }),
  z.object({ ...common, visual_family: z.literal("process"), process_kind: z.enum(["linear", "cyclic", "branched", "unknown"]), stages: z.array(entity).max(24), edges: z.array(edge).max(40), starts: z.array(id).max(8), ends: z.array(id).max(8) }),
  z.object({ ...common, visual_family: z.literal("map"), states: z.array(z.object({ id, label, features: z.array(entity.extend({ location })).max(24) })).min(1).max(4), changes: z.array(z.object({ kind: z.enum(["addition", "removal", "replacement", "relocation", "expansion", "unchanged"]), from_state: id, to_state: id, before: id.nullable(), after: id.nullable(), location })).max(24) }),
  z.object({ ...common, visual_family: z.literal("system"), components: z.array(entity).max(24), connections: z.array(edge).max(40), inputs: z.array(id).max(8), outputs: z.array(id).max(8) }),
  z.object({ ...common, visual_family: z.literal("other"), entities: z.array(entity).max(24), relationships: z.array(edge).max(30), observations: z.array(z.string().min(1).max(240)).max(8) }),
]);
const factKinds = ["value", "min", "max", "start", "end", "absolute_change", "percentage_change", "rank", "rank_change", "largest_increase", "largest_decrease", "stable", "overall_direction", "crossover"] as const;
export const task1AnalysisSchema = z.object({
  visual_family: z.enum(["chart_table", "process", "map", "system", "other"]), confidence,
  reference: visualReferenceSchema.nullable(),
  cross_check: z.object({
    specialist_used: z.boolean(), specialist_model: z.string().max(160), specialist_revision: z.string().max(80),
    status: z.enum(["COMPLETED", "UNAVAILABLE", "PARSE_FAILED", "RECONCILIATION_FAILED"]),
    agreement_count: z.number().int().min(0).max(2000), disagreement_count: z.number().int().min(0).max(2000),
    unmatched_primary_count: z.number().int().min(0).max(2000), unmatched_specialist_count: z.number().int().min(0).max(2000), unknown_count: z.number().int().min(0).max(2000),
    warnings: z.array(z.enum(["CHART_SPECIALIST_UNAVAILABLE", "CHART_SPECIALIST_PARSE_FAILED", "CHART_RECONCILIATION_FAILED", "CHART_DATA_DISAGREEMENT", "CHART_ALIGNMENT_UNCERTAIN", "CHART_CELLS_UNPARSEABLE"])).max(6),
  }).nullable().optional(),
  derived_facts: z.array(z.object({ id: z.string().max(40), component_id: z.string().max(40), kind: z.enum(factKinds), subjects: z.array(label).min(1).max(12), category: z.string().max(120).nullable(), end_category: z.string().max(120).nullable(), value: decimal.pipe(z.number().min(-1e24).max(1e24)).nullable(), direction: z.enum(["increase", "decrease", "stable"]).nullable() })).max(1600),
  claims: z.array(z.object({ claim_id: z.string().max(40), source_ids: z.array(z.string().regex(/^P[1-9]\d*S[1-9]\d*$/)).min(1).max(3), quote: z.string().min(1).max(12000), claim: z.string().max(400), verdict: z.enum(["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE"]), explanation: z.string().min(1).max(400), evidence: z.array(z.string()).max(8) })).max(20),
  warnings: z.array(z.enum(["VISUAL_LOW_CONFIDENCE", "VISUAL_GROUNDING_FAILED", "DERIVED_FACTS_FAILED", "CLAIM_EXTRACTION_FAILED", "CLAIM_VERIFICATION_FAILED", "CHART_SPECIALIST_UNAVAILABLE", "CHART_SPECIALIST_PARSE_FAILED", "CHART_RECONCILIATION_FAILED", "CHART_DATA_DISAGREEMENT", "CHART_ALIGNMENT_UNCERTAIN", "CHART_CELLS_UNPARSEABLE"])).max(11),
});
export type Task1Analysis = z.infer<typeof task1AnalysisSchema>;
