// Isolated component preview. Never connects to an application backend or provider.
import { createRoot } from "react-dom/client";
import { AppShell } from "@/components/ui/app-shell";
import { PersonalizationProvider } from "@/features/personalization/personalization-provider";
import { SpeakingBenchmarkList } from "@/features/speaking-benchmark/sample-list";
import { SpeakingBenchmarkDetail } from "@/features/speaking-benchmark/sample-detail";
import { BlindReviewer } from "@/features/speaking-benchmark/blind-reviewer";
import { ResearchList } from "@/features/speaking-benchmark/research/research-list";
import { ResearchDetail } from "@/features/speaking-benchmark/research/research-detail";
import { AssignedReviews } from "@/features/speaking-benchmark/assigned-reviews";
import { cohort, experiment, researchReport } from "./research-fixtures";
import { questionJob, rater, assignment, assessment, adjudication, comparison, gradingRun, summary } from "./workflow-fixtures";
import { QualityDashboard } from "@/features/speaking-benchmark/quality/quality-dashboard";
import { SuiteManager } from "@/features/speaking-benchmark/quality/suite-manager";
import { GateManager } from "@/features/speaking-benchmark/quality/gate-manager";
import { SpeakingBenchmarkReports } from "@/features/speaking-benchmark/evaluation/reports";
import { labSample, labAvailable, labReview, labLabels } from "../speaking-benchmark-fixtures";
import "@fontsource-variable/raleway";
import "@/app/globals.css";
import "@/app/design-system.css";
import "@/app/gravity-product.css";

const params = new URLSearchParams(location.search);
localStorage.setItem("ielts-theme", params.get("theme") ?? "light");
localStorage.setItem("ielts-accent", params.get("accent") ?? "PURPLE");
localStorage.setItem("ielts-locale", params.get("locale") ?? "en");
const suite = { id: "synthetic-suite", family_id: "synthetic-family", revision: 1, name: "Synthetic DEV release suite", description: "Authorized fictional fixtures only", configuration: { cohort: [{ sample_id: labSample.id, review_revision: 1 }], holdout_evaluation: false }, fingerprint: "a".repeat(64), frozen_at: "2026-11-09T00:00:00Z", created_at: "2026-11-09T00:00:00Z" };
const gate = { id: "synthetic-gate", name: "Synthetic ASR release check", suite_id: suite.id, baseline: { kind: "GRADING", configuration_fingerprint: "a".repeat(64) }, candidate: { kind: "GRADING", configuration_fingerprint: "b".repeat(64) }, policy: { protocol: "speaking-regression-gate-v1", comparison: "CONFIGURATION", minimum_independent_candidates: 10, minimum_prediction_coverage: 1, minimum_reference_coverage: 1, thresholds: [{ metric: "wer", max_regression: 0.01 }], max_unknown_billing_attempts: 0 }, fingerprint: "c".repeat(64), created_at: suite.created_at };
const report = { id: "synthetic-report", gate_id: gate.id, status: "INCONCLUSIVE", protocol: gate.policy.protocol, fingerprint: "d".repeat(64), created_at: suite.created_at, report: { matched_samples: 1, matched_independent_candidates: 1, reasons: ["INSUFFICIENT_MATCHED_INDEPENDENT_CANDIDATES"], metrics: [{ metric: "wer", baseline: 0.12, candidate: 0.13, difference: 0.01, relative_difference: 0.0833, tolerable_regression: 0.01, status: "INCONCLUSIVE", paired: { ci95: null, matched_samples: 1 } }], candidate_unknown_billing_requests: 0 } };
window.fetch = async (input, init) => {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, location.origin);
  const path = url.pathname;
  let body: unknown = [];
  if (path.endsWith("/grading-availability")) body = { can_queue: true, live_status: "SYNTHETIC_FIXTURE", execution: "local", providers: [{ provider: "azure_pa", available: true, reasons: [], additional_audio_request: false, gpu: false }] };
  else if (path.endsWith("/availability")) body = labAvailable;
  else if (path.endsWith("/samples")) body = { items: params.get("state") === "empty" ? [] : [labSample], total: params.get("state") === "empty" ? 0 : 1, offset: 0, limit: 25 };
  else if (path.endsWith(`/samples/${labSample.id}`)) body = labSample;
  else if (path.endsWith("/review")) body = labReview;
  else if (path.endsWith("/human-labels")) body = labLabels;
  else if (path.endsWith("/grading-reviews")) body = [{ revision: 1, approved_at: suite.created_at }];
  else if (path.endsWith("/grading/preflight")) body = { preflight_fingerprint: "e".repeat(64), config_fingerprint: "f".repeat(64), configuration: {}, review_revision: 1, candidate_ms: 3000, window_count: 1, parts: [1], windows: [{ id: "synthetic-window", part_number: 1, start_ms: 2000, end_ms: 5000 }], requests: { azure_pa: 1, openai_typical: 8, openai_maximum: 20 }, warnings: [], can_queue: true, blockers: [] };
  else if (path.endsWith("/grading-runs")) body = [params.get("state") === "partial" ? { ...gradingRun, status: "PARTIAL" } : gradingRun];
  else if (path.endsWith("/comparison")) body = comparison;
  else if (path.endsWith("/reports/summary")) body = summary;
  else if (path.endsWith("/reports/samples")) body = { items: [comparison], total: 1, offset: 0, limit: 25, configuration: comparison.configuration, chart_points: [comparison], chart_limit: 2000, chart_sampled: false };
  else if (path.endsWith("/question-suggestions")) body = [questionJob];
  else if (path.endsWith("/quality")) body = { protocol: "speaking-dataset-quality-v1", evaluated_at: suite.created_at, status: "INSUFFICIENT_DATA", issues: [{ code: "MINIMUM_INDEPENDENT_CANDIDATES", severity: "INSUFFICIENT_DATA", artifact: "cohort", artifact_id: "synthetic-cohort", remediation: "Add independently assessed candidates before making a release decision." }], samples: [], issue_counts: { INSUFFICIENT_DATA: 1 }, eligible_samples: 0, ineligible_samples: 1, independent_candidates: 1, fingerprint: suite.fingerprint };
  else if (path.endsWith("/evaluation-suites")) body = [suite];
  else if (path.endsWith(`/evaluation-suites/${suite.id}`)) body = suite;
  else if (path.endsWith("/regression-gates")) body = [gate];
  else if (path.endsWith("/reports") && path.includes("regression-gates")) body = [report];
  else if (path.endsWith("/research/cohort")) body = [cohort];
  else if (path.endsWith("/research/experiments")) body = [{ id: experiment.id, name: experiment.name, mode: experiment.mode, status: "COMPLETED", created_at: suite.created_at, sample_count: 1, providers: ["azure_pa"] }];
  else if (path.endsWith(`/experiments/${experiment.id}`)) body = { ...experiment, status: "COMPLETED" };
  else if (path.endsWith(`/experiments/${experiment.id}/results`)) body = researchReport;
  else if (path.endsWith("/reviewer-assignments/synthetic-assignment")) body = { id: "synthetic-assignment", sample_id: labSample.id, review_revision: 1, source_sha256: labSample.source_sha256, manifest_fingerprint: suite.fingerprint, revision: 1, duration_ms: 60000, audio_url: "/synthetic-audio", questions: [], assessments: [], created_at: suite.created_at };
  else if (/\/(human-raters|rater-assignments|human-assessments|adjudications|reviewer-assignments)$/.test(path)) {
    const items = path.endsWith("/human-raters") ? [rater] : path.endsWith("/human-assessments") ? [assessment] : path.endsWith("/adjudications") ? [adjudication] : [assignment];
    body = { items, total: items.length, offset: 0, limit: 25 };
  }
  else if (path.includes("/notifications")) body = { items: [], total: 0, unread_count: 0 };
  else if (path.endsWith("/audio")) return new Response(null, { status: 204 });
  // A fixture rejects unknown mutations rather than ever forwarding them.
  else if (init?.method && init.method !== "GET") return new Response(JSON.stringify({ code: "UX_FIXTURE_ONLY", message: "This preview does not execute provider calls." }), { status: 422 });
  return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
};
const screen = params.get("screen") ?? "list";
const screens: Record<string, React.ReactNode> = { list: <SpeakingBenchmarkList />, detail: <SpeakingBenchmarkDetail sampleId={labSample.id} />, human: <BlindReviewer assignmentId="synthetic-assignment" />, research: <ResearchList />, experiment: <ResearchDetail experimentId={experiment.id} />, quality: <QualityDashboard />, suites: <SuiteManager />, gates: <GateManager />, reports: <SpeakingBenchmarkReports />, assignments: <AssignedReviews /> };
createRoot(document.getElementById("root")!).render(<PersonalizationProvider><AppShell currentYear={2026}><p className="notice">SYNTHETIC UX FIXTURE · No private recordings or provider calls</p>{screens[screen]}</AppShell></PersonalizationProvider>);
