import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { SpeakingEvaluation } from "@/features/speaking-benchmark/evaluation/speaking-evaluation";
import { SpeakingBenchmarkReports } from "@/features/speaking-benchmark/evaluation/reports";
import * as api from "@/lib/api/speaking-benchmark-grading";

vi.mock("@/lib/api/speaking-benchmark-grading", async original => ({
  ...await original<typeof api>(),
  gradingAvailability: vi.fn(),
  approvedReviews: vi.fn(),
  listRuns: vi.fn(),
  prepareGrading: vi.fn(),
  submitGrading: vi.fn(),
  cancelGrading: vi.fn(),
  retryGrading: vi.fn(),
  runComparison: vi.fn(),
  reportSummary: vi.fn(),
  reportSamples: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.gradingAvailability).mockResolvedValue({
    can_queue: false,
    live_status: "LIVE_UNVERIFIED",
    execution: "local",
    providers: [{ provider: "azure_pa", available: false, reasons: ["SPEAKING_BENCHMARK_GRADING_DISABLED"], additional_audio_request: false, gpu: false }],
  });
  vi.mocked(api.approvedReviews).mockResolvedValue([{ revision: 3, approved_at: "2026-11-08T00:00:00Z" }]);
  vi.mocked(api.listRuns).mockResolvedValue([]);
  vi.mocked(api.runComparison).mockResolvedValue({
    sample_id: "fixture",
    code: "SAMPLE-001",
    split: "DEV",
    run_id: "run-1",
    configuration: "b".repeat(64),
    review_revision: 3,
    label_revision: 1,
    verified: true,
    label_status: "HUMAN_VERIFIED",
    human: { fc: 6.5, lr: 6, gra: 6.5, pr: 7, overall: 6.5 },
    ai: { fc: 6.5, lr: 6, gra: 6, pr: 6.5, overall: 6.5 },
    differences: { fc: 0, lr: 0, gra: -0.5, pr: -0.5, overall: 0 },
    status: "COMPLETED",
    candidate_ms: 25800,
    latency_ms: 4500,
    model: "gpt-6-luna",
    rubric_version: "2026",
    prompt_version: "hybrid-v1",
    limitations: [],
  });
});

it("queues only after preflight, complete estimates, disclosures and final confirmation", async () => {
  vi.mocked(api.gradingAvailability).mockResolvedValue({
    can_queue: true,
    live_status: "LIVE_UNVERIFIED",
    execution: "local",
    providers: [{ provider: "azure_pa", available: true, reasons: [], additional_audio_request: false, gpu: false }],
  });
  vi.mocked(api.prepareGrading).mockResolvedValue({
    preflight_fingerprint: "a".repeat(64),
    config_fingerprint: "b".repeat(64),
    configuration: { lexical_provider: "azure_pa" },
    review_revision: 3,
    candidate_ms: 25800,
    window_count: 1,
    parts: [1, 2, 3],
    windows: [{ id: "candidate", part_number: 2, start_ms: 21000, end_ms: 35000 }],
    requests: { azure_pa: 1, openai_typical: 8, openai_maximum: 20 },
    warnings: [],
    can_queue: true,
    blockers: [],
  });
  vi.mocked(api.submitGrading).mockResolvedValue({
    id: "run-1",
    sample_id: "fixture",
    review_revision: 3,
    config_fingerprint: "b".repeat(64),
    configuration: { lexical_provider: "azure_pa" },
    candidate_ms: 25800,
    window_count: 1,
    status: "PENDING",
    stage: "queued",
    progress: 0,
    error_code: null,
    prediction: null,
    created_at: "2026-11-08T00:00:00Z",
    started_at: null,
    finished_at: null,
    requests: [],
  });
  const play = vi.fn();
  renderWithLocale(<SpeakingEvaluation sampleId="fixture" labelRevision={1} onPlay={play} />);
  await screen.findByRole("option", { name: /3 ·/ });
  fireEvent.change(screen.getByLabelText("Approved review revision"), { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "Check selected revision" }));
  const queue = await screen.findByRole("button", { name: "Authorize and queue evaluation" });
  expect(queue).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /2 · 21.0–35.0 s/ }));
  expect(play).toHaveBeenCalledWith(21000, 35000);
  fireEvent.change(screen.getByLabelText("azure_pa · Admission estimate (USD)"), { target: { value: ".2" } });
  fireEvent.change(screen.getByLabelText("openai · Admission estimate (USD)"), { target: { value: ".3" } });
  fireEvent.change(screen.getByLabelText("Maximum total estimate (USD)"), { target: { value: "1" } });
  fireEvent.click(screen.getByLabelText(/I authorize sending only/));
  fireEvent.click(screen.getByLabelText(/I authorize sending transcript/));
  expect(api.submitGrading).not.toHaveBeenCalled();
  fireEvent.click(queue);
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Authorize and queue evaluation" }));
  await waitFor(() => expect(api.submitGrading).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.submitGrading).mock.calls[0][5]).toEqual({
    azure_audio: true,
    llm_text: true,
    independent_provider: false,
    estimates_usd: { azure_pa: 0.2, openai: 0.3 },
    max_estimated_cost_usd: 1,
  });
});

it("loads static readiness without starting inference and requires explicit approved selection", async () => {
  renderWithLocale(<SpeakingEvaluation sampleId="fixture" labelRevision={1} onPlay={vi.fn()} />);
  expect(await screen.findByText("SPEAKING_BENCHMARK_GRADING_DISABLED")).toBeInTheDocument();
  expect(api.prepareGrading).not.toHaveBeenCalled();
  expect(api.submitGrading).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Check selected revision" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Approved review revision"), { target: { value: "3" } });
  expect(api.submitGrading).not.toHaveBeenCalled();
});

it("allows cancelling active run and displays human vs ai comparison", async () => {
  const activeRun: api.GradingRun = {
    id: "run-active",
    sample_id: "fixture",
    review_revision: 3,
    config_fingerprint: "b".repeat(64),
    configuration: { lexical_provider: "azure_pa" },
    candidate_ms: 25800,
    window_count: 1,
    status: "RUNNING",
    stage: "azure_pa",
    progress: 30,
    error_code: null,
    prediction: null,
    created_at: "2026-11-08T00:00:00Z",
    started_at: "2026-11-08T00:00:01Z",
    finished_at: null,
    requests: [],
  };
  vi.mocked(api.listRuns).mockResolvedValue([activeRun]);
  vi.mocked(api.cancelGrading).mockResolvedValue({ ...activeRun, status: "CANCELLED" });

  renderWithLocale(<SpeakingEvaluation sampleId="fixture" labelRevision={1} onPlay={vi.fn()} />);
  await screen.findByText(/RUNNING · azure_pa · 30%/);
  const cancelButton = screen.getByRole("button", { name: "Cancel evaluation" });
  fireEvent.click(cancelButton);
  await waitFor(() => expect(api.cancelGrading).toHaveBeenCalledWith("fixture", "run-active"));
});

it("supports historical label revision refresh in comparison table", async () => {
  const completedRun: api.GradingRun = {
    id: "run-done",
    sample_id: "fixture",
    review_revision: 3,
    config_fingerprint: "b".repeat(64),
    configuration: { lexical_provider: "azure_pa" },
    candidate_ms: 25800,
    window_count: 1,
    status: "COMPLETED",
    stage: "completed",
    progress: 100,
    error_code: null,
    prediction: {
      bands: { fc: 6.5, lr: 6, gra: 6, pr: 6.5, overall: 6.5 },
      criteria: {},
      limitations: [],
      advisory: true,
    },
    created_at: "2026-11-08T00:00:00Z",
    started_at: "2026-11-08T00:00:01Z",
    finished_at: "2026-11-08T00:00:05Z",
    requests: [],
  };
  vi.mocked(api.listRuns).mockResolvedValue([completedRun]);

  renderWithLocale(<SpeakingEvaluation sampleId="fixture" labelRevision={1} onPlay={vi.fn()} />);
  await screen.findByText("Human reference");
  expect(screen.getByText("AI prediction")).toBeInTheDocument();

  // Changing label revision and clicking refresh calls runComparison with label=2
  const labelInput = screen.getByLabelText("Human label revision");
  fireEvent.change(labelInput, { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Refresh comparison only" }));
  await waitFor(() => expect(api.runComparison).toHaveBeenCalledWith("fixture", "run-done", 2));
});

it("renders reports dashboard with summary metrics, charts and export links", async () => {
  const metricFixture = {
    total_count: 10,
    count: 10,
    nonscorable_count: 0,
    coverage_rate: 1.0,
    mae: 0.35,
    rmse: 0.42,
    signed_bias: -0.1,
    exact_agreement: 0.6,
    within_0_5: 0.9,
    within_1_0: 1.0,
    pearson: 0.85,
    spearman: 0.82,
    quadratic_weighted_kappa: 0.8,
    pearson_status: "AVAILABLE",
    spearman_status: "AVAILABLE",
    qwk_status: "AVAILABLE",
  };
  vi.mocked(api.reportSummary).mockResolvedValue({
    schema_version: "2026-11-08-speaking-evaluation-report-v1",
    selection_policy: "latest-finalized-per-sample-single-configuration-v1",
    date_filter: "sample_uploaded_at",
    configuration: "b".repeat(64),
    configurations: ["b".repeat(64)],
    requires_configuration: false,
    eligible_samples: 10,
    displayed_samples: 10,
    uploaded_samples: 12,
    unlabelled_or_ineligible: 2,
    criteria: {
      fc: metricFixture,
      lr: metricFixture,
      gra: metricFixture,
      pr: metricFixture,
      overall: metricFixture,
    },
    split_metrics: {
      DEV: {
        eligible_samples: 5,
        displayed_samples: 5,
        criteria: {
          overall: metricFixture,
        },
      },
    },
    warnings: [],
    leaking_speaker_count: 0,
  });

  vi.mocked(api.reportSamples).mockResolvedValue({
    items: [{
      sample_id: "s1",
      code: "CAND-001",
      split: "DEV",
      run_id: "run-1",
      configuration: "b".repeat(64),
      review_revision: 1,
      label_revision: 1,
      verified: true,
      label_status: "HUMAN_VERIFIED",
      human: { overall: 6.5 },
      ai: { overall: 6.5 },
      differences: { overall: 0 },
      status: "COMPLETED",
      candidate_ms: 30000,
      latency_ms: 4000,
      model: "gpt-6-luna",
      rubric_version: "2026",
      prompt_version: "v1",
      limitations: [],
    }],
    total: 1,
    offset: 0,
    limit: 25,
    configuration: "b".repeat(64),
    chart_points: [{
      sample_id: "s1",
      code: "CAND-001",
      split: "DEV",
      run_id: "run-1",
      configuration: "b".repeat(64),
      review_revision: 1,
      label_revision: 1,
      verified: true,
      label_status: "HUMAN_VERIFIED",
      human: { overall: 6.5 },
      ai: { overall: 6.5 },
      differences: { overall: 0 },
      status: "COMPLETED",
      candidate_ms: 30000,
      latency_ms: 4000,
      model: "gpt-6-luna",
      rubric_version: "2026",
      prompt_version: "v1",
      limitations: [],
    }],
    chart_limit: 500,
    chart_sampled: false,
    outliers: [{
      sample_id: "s1",
      code: "CAND-001",
      split: "DEV",
      run_id: "run-1",
      configuration: "b".repeat(64),
      review_revision: 1,
      label_revision: 1,
      verified: true,
      label_status: "HUMAN_VERIFIED",
      human: { overall: 6.5 },
      ai: { overall: 6.5 },
      differences: { overall: 0 },
      status: "COMPLETED",
      candidate_ms: 30000,
      latency_ms: 4000,
      model: "gpt-6-luna",
      rubric_version: "2026",
      prompt_version: "v1",
      limitations: [],
    }],
  });

  renderWithLocale(<SpeakingBenchmarkReports />);
  await screen.findByText("Speaking evaluation reports");
  expect(screen.getByText("Eligible human-labelled samples")).toBeInTheDocument();
  expect(screen.getByText("Export filtered CSV")).toBeInTheDocument();
  expect(screen.getByText("Export filtered JSON")).toBeInTheDocument();
  expect(screen.getAllByText("CAND-001").length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText(/Global Outliers/)).toBeInTheDocument();
});
