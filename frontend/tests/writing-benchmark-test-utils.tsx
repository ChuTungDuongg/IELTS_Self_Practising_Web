import { vi } from "vitest";
import * as api from "@/lib/api/writing-benchmark";
import { benchmarkSample, benchmarkSummary, otherId } from "./writing-benchmark-fixtures";

export function setupBenchmarkApi() {
  const rows = new Map<string, api.BenchmarkSample>([
    [benchmarkSample().id, api.benchmarkSampleSchema.parse(benchmarkSample())],
    [otherId, api.benchmarkSampleSchema.parse(benchmarkSample({ id: otherId, code: "T1-002", sequence_number: 2, prompt: "Second fictional prompt" }))],
  ]);
  vi.mocked(api.getWritingBenchmarkSummary).mockImplementation(async () => {
    const summary = api.benchmarkSummarySchema.parse(benchmarkSummary());
    for (const task of summary.tasks) {
      const samples = [...rows.values()].filter(row => row.task_number === task.task_number);
      task.total = samples.length; task.complete = samples.filter(row => row.status === "COMPLETE").length;
      task.draft = task.total - task.complete;
    }
    return summary;
  });
  vi.mocked(api.listWritingBenchmarkSamples).mockImplementation(async task => [...rows.values()].filter(row => row.task_number === task).map(row => {
    const keys = new Set(["prompt", "essay", "task1_task_type", "source_note", "redistributable"]);
    return api.benchmarkSampleListSchema.parse(Object.fromEntries(Object.entries(row).filter(([key]) => !keys.has(key))));
  }));
  vi.mocked(api.getWritingBenchmarkSample).mockImplementation(async id => rows.get(id)!);
  vi.mocked(api.createWritingBenchmarkSample).mockImplementation(async task => {
    const row = api.benchmarkSampleSchema.parse(benchmarkSample({ id: "10000000-0000-4000-8000-000000000003", task_number: task, code: `T${task}-003`, sequence_number: 3, human_scores: task === 1 ? { ta: null, cc: null, lr: null, gra: null } : { tr: null, cc: null, lr: null, gra: null } }));
    rows.set(row.id, row); return row;
  });
  vi.mocked(api.updateWritingBenchmarkSample).mockImplementation(async (id, patch) => {
    const { expected_revision: revision, ...edits } = patch;
    const current = rows.get(id)!;
    const saved = api.benchmarkSampleSchema.parse({ ...current, ...edits, human_scores: { ...current.human_scores, ...edits.human_scores }, revision: revision + 1 });
    rows.set(id, saved); return saved;
  });
  vi.mocked(api.completeWritingBenchmarkSample).mockImplementation(async (id, revision) => {
    const saved = { ...rows.get(id)!, status: "COMPLETE" as const, revision: revision + 1 };
    rows.set(id, saved); return saved;
  });
  vi.mocked(api.deleteWritingBenchmarkSample).mockImplementation(async id => { rows.delete(id); });
  vi.mocked(api.uploadWritingBenchmarkImage).mockImplementation(async (id, _file, revision) => {
    const saved = { ...rows.get(id)!, has_image: true, revision: revision + 1 };
    rows.set(id, saved); return saved;
  });
  vi.mocked(api.removeWritingBenchmarkImage).mockImplementation(async (id, revision) => {
    const saved = { ...rows.get(id)!, has_image: false, status: "DRAFT" as const, revision: revision + 1 };
    rows.set(id, saved); return saved;
  });
  return rows;
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
