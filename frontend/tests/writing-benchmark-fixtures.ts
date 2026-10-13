export const sampleId = "10000000-0000-4000-8000-000000000001";
export const otherId = "10000000-0000-4000-8000-000000000002";

export function benchmarkSample(overrides: Record<string, unknown> = {}) {
  return { id: sampleId, code: "T1-001", task_number: 1, sequence_number: 1,
    status: "DRAFT", split: "DEV", human_scores: { ta: null, cc: null, lr: null, gra: null },
    human_overall: null, has_image: false, revision: 1,
    created_at: "2026-10-13T00:00:00Z", updated_at: "2026-10-13T00:00:00Z",
    prompt: "", essay: "", task1_task_type: null, source_note: null, redistributable: false,
    ...overrides };
}

export function benchmarkList(overrides: Record<string, unknown> = {}) {
  const { prompt: _prompt, essay: _essay, task1_task_type: _type, source_note: _source, redistributable: _rights, ...item } = benchmarkSample(overrides);
  return item;
}

export function benchmarkSummary() {
  return { tasks: [1, 2].map(task_number => ({ task_number, capacity: 100, total: 0, draft: 0, complete: 0,
    split_counts: { DEV: 0, HOLDOUT: 0 }, split_targets: { DEV: 80, HOLDOUT: 20 },
    overall_distribution: Array.from({ length: 19 }, (_, i) => ({ band: i / 2, actual: 0, suggested: i < 8 ? null : [8, 8, 9, 10, 11, 12, 12, 10, 8, 6, 6][i - 8] })),
  })) };
}
