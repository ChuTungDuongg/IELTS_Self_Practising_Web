import type { Comparison, ReportSummary } from "@/lib/api/speaking-benchmark-grading";
import { comparison, summary } from "./workflow-fixtures";

// Fictional scores for layout checks. These never leave the isolated preview.
const criteria = ["fc", "lr", "gra", "pr", "overall"];
const emptyMetric = {
  total_count: 0, count: 0, nonscorable_count: 0, coverage_rate: null,
  mae: null, rmse: null, signed_bias: null, exact_agreement: null,
  within_0_5: null, within_1_0: null, pearson: null, spearman: null,
  quadratic_weighted_kappa: null, pearson_status: "INSUFFICIENT_DATA",
  spearman_status: "INSUFFICIENT_DATA", qwk_status: "INSUFFICIENT_DATA",
};
export const emptyReport: ReportSummary = {
  ...summary, configuration: null, configurations: [], uploaded_samples: 0,
  eligible_samples: 0, displayed_samples: 0,
  criteria: Object.fromEntries(criteria.map(key => [key, { ...emptyMetric }])),
  split_metrics: Object.fromEntries(["DEV", "HOLDOUT"].map(key => [key, {
    eligible_samples: 0, displayed_samples: 0, criteria: { overall: { ...emptyMetric } },
  }])),
};
export const reportComparisons: Comparison[] = Array.from({ length: 24 }, (_, index) => {
  const human = 5.5 + index % 5 * 0.5;
  const difference = [-0.5, 0, 0.5, 0, 1, 0][index % 6];
  return {
    ...comparison, sample_id: `fictional-${index}`, code: `SYNTH-${String(index + 1).padStart(3, "0")}`,
    split: index < 12 ? "DEV" : "HOLDOUT",
    human: Object.fromEntries(criteria.map(key => [key, human])),
    ai: Object.fromEntries(criteria.map(key => [key, human + difference])),
    differences: Object.fromEntries(criteria.map(key => [key, difference])),
  };
});
function metricFor(rows: Comparison[]) {
  const differences = rows.map(row => row.differences.overall!);
  const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / rows.length;
  return {
    ...emptyMetric, total_count: rows.length, count: rows.length, coverage_rate: 1,
    mae: mean(differences.map(Math.abs)), rmse: Math.sqrt(mean(differences.map(value => value ** 2))),
    signed_bias: mean(differences), exact_agreement: differences.filter(value => value === 0).length / rows.length,
    within_0_5: differences.filter(value => Math.abs(value) <= 0.5).length / rows.length,
    within_1_0: differences.filter(value => Math.abs(value) <= 1).length / rows.length,
    pearson_status: "NOT_CALCULATED_IN_FIXTURE", spearman_status: "NOT_CALCULATED_IN_FIXTURE", qwk_status: "NOT_CALCULATED_IN_FIXTURE",
  };
}
export const filledReport: ReportSummary = {
  ...summary, uploaded_samples: 24, eligible_samples: 24, displayed_samples: 24,
  criteria: Object.fromEntries(criteria.map(key => [key, metricFor(reportComparisons)])),
  split_metrics: Object.fromEntries(["DEV", "HOLDOUT"].map(split => [split, {
    eligible_samples: 12, displayed_samples: 12, criteria: { overall: metricFor(reportComparisons.filter(row => row.split === split)) },
  }])),
};
