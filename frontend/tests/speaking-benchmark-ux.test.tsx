import { useState } from "react";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { labSample } from "./speaking-benchmark-fixtures";
import { LabNavigation } from "@/features/speaking-benchmark/lab-navigation";
import { PersistentSections } from "@/features/speaking-benchmark/persistent-sections";
import { HumanAdjudicationPanel } from "@/features/speaking-benchmark/human-adjudication-panel";
import { SuiteManager } from "@/features/speaking-benchmark/quality/suite-manager";
import { GateManager } from "@/features/speaking-benchmark/quality/gate-manager";
import { GateReport } from "@/features/speaking-benchmark/quality/gate-report";
import { QualityDashboard } from "@/features/speaking-benchmark/quality/quality-dashboard";
import * as human from "@/lib/api/speaking-benchmark-human";
import * as quality from "@/lib/api/speaking-benchmark-quality";
import { en } from "@/lib/i18n/en";

vi.mock("@/lib/api/speaking-benchmark", () => ({ listSpeakingSamples: vi.fn(() => Promise.resolve({ items: [{ ...labSample, status: "APPROVED" }], total: 1 })) }));
vi.mock("@/lib/api/speaking-benchmark-human", async original => ({ ...await original<typeof human>(), listRaters: vi.fn(), listAssignments: vi.fn(), listAssessments: vi.fn(), listAdjudications: vi.fn(), humanAgreement: vi.fn(), adjudicate: vi.fn() }));
vi.mock("@/lib/api/speaking-benchmark-quality", async original => ({ ...await original<typeof quality>(), listSuites: vi.fn(), createSuite: vi.fn(), listGates: vi.fn(), createGate: vi.fn(), gateReports: vi.fn(), qualitySnapshots: vi.fn(), evaluateQuality: vi.fn() }));

const bands = { fc: null, lr: null, gra: null, pr: null, overall: 6.5 };
const assessment: human.HumanAssessment = { id: "assessment", assignment_id: "assignment", sample_id: labSample.id, rater_id: "rater", review_revision: 1, source_sha256: labSample.source_sha256, manifest_fingerprint: "b".repeat(64), revision: 1, status: "SUBMITTED", bands, comments: { fc: "", lr: "", gra: "", pr: "", overall: "Fictional independent report" }, independently_performed: true, provenance: "external_verified_report", source_reference: "Synthetic report", eligible: true, authored_by: "owner", submitted_at: labSample.created_at };
const suite: quality.EvaluationSuite = { id: "suite", family_id: "family", revision: 1, name: "Fictional DEV suite", description: "Fictional fixtures", configuration: {}, fingerprint: "b".repeat(64), frozen_at: labSample.created_at, created_at: labSample.created_at };
const gate: quality.RegressionGate = { id: "gate", name: "Fictional comparison", suite_id: suite.id, baseline: { kind: "GRADING", configuration_fingerprint: "a".repeat(64) }, candidate: { kind: "GRADING", configuration_fingerprint: "b".repeat(64) }, policy: { protocol: "speaking-regression-gate-v1", comparison: "CONFIGURATION", minimum_independent_candidates: 10, minimum_prediction_coverage: 1, minimum_reference_coverage: 1, thresholds: [{ metric: "wer", max_regression: 0 }], max_unknown_billing_attempts: 0 }, fingerprint: "c".repeat(64), created_at: labSample.created_at };

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  vi.mocked(human.listRaters).mockResolvedValue({ items: [{ id: "rater", kind: "EXTERNAL", display_name: "Fictional reviewer", user_id: null, external_key: "fixture", created_at: labSample.created_at }], total: 1, offset: 0, limit: 25 });
  vi.mocked(human.listAssignments).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25 });
  vi.mocked(human.listAssessments).mockResolvedValue({ items: [assessment], total: 1, offset: 0, limit: 25 });
  vi.mocked(human.listAdjudications).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25 });
  vi.mocked(quality.listSuites).mockResolvedValue([suite]);
  vi.mocked(quality.listGates).mockResolvedValue([]);
  vi.mocked(quality.gateReports).mockResolvedValue([]);
  vi.mocked(quality.createSuite).mockResolvedValue(suite);
  vi.mocked(quality.createGate).mockResolvedValue(gate);
  vi.mocked(quality.qualitySnapshots).mockResolvedValue([]);
});

it("uses four lab sections and places release tools in a labelled subnavigation", () => {
  renderWithLocale(<LabNavigation current="quality" tool="gates" />);
  const nav = screen.getByRole("navigation", { name: "Speaking lab sections" });
  expect(within(nav).getByRole("link", { name: "Recordings" })).toHaveAttribute("href", "/admin/speaking-benchmark");
  expect(within(nav).getByRole("link", { name: "AI Evaluation" })).toHaveAttribute("href", "/admin/speaking-benchmark/reports");
  const release = screen.getByRole("navigation", { name: "Quality & release" });
  expect(within(release).getByRole("link", { name: "Regression Gates" })).toHaveAttribute("aria-current", "page");
  fireEvent.click(screen.getByText("Tasks & other labs"));
  expect(screen.getByRole("link", { name: "My blind review assignments" })).toHaveAttribute("href", "/admin/speaking-benchmark/reviewer");
  expect(screen.getByRole("link", { name: "Writing benchmark bank" })).toHaveAttribute("href", "/admin/writing-benchmark");
  fireEvent.keyDown(screen.getByText("Tasks & other labs"), { key: "Escape" });
  expect(screen.getByText("Tasks & other labs").closest("details")).not.toHaveAttribute("open");
});

it("keeps local form state and DOM identity through keyboard and mobile section selection", () => {
  function Editor() { const [text, setText] = useState(""); return <label>Independent notes<input value={text} onChange={event => setText(event.target.value)} /></label>; }
  renderWithLocale(<PersistentSections label="Recording areas" sections={[{ id: "one", label: "Preparation", content: <Editor /> }, { id: "two", label: "Research", content: <p>Research area</p> }]} />);
  const input = screen.getByLabelText("Independent notes");
  fireEvent.change(input, { target: { value: "Retain this draft" } });
  const first = screen.getByRole("tab", { name: "Preparation" });
  fireEvent.keyDown(first, { key: "End" });
  expect(screen.getByRole("tab", { name: "Research" })).toHaveFocus();
  expect(input).not.toBeVisible();
  fireEvent.change(screen.getByRole("combobox", { name: "Recording areas" }), { target: { value: "one" } });
  expect(screen.getByLabelText("Independent notes")).toBe(input);
  expect(input).toHaveValue("Retain this draft");
  expect(first).toHaveAttribute("aria-controls", input.closest('[role="tabpanel"]')!.id);
});

it("preserves adjudication bands through work areas and submits the original source-bound assessment", async () => {
  const dirty = vi.fn();
  vi.mocked(human.adjudicate).mockResolvedValue({ id: "adj", sample_id: labSample.id, review_revision: 1, source_sha256: labSample.source_sha256, manifest_fingerprint: "b".repeat(64), revision: 1, assessment_refs: [], bands, rationale: "Independent consensus", policy_version: "human-adjudication-v1", provenance: "owner", adjudicator_id: "owner", adjudicated_at: labSample.created_at });
  renderWithLocale(<HumanAdjudicationPanel sampleId={labSample.id} reviewRevision={1} onDirty={dirty} />);
  await waitFor(() => expect(human.listAssessments).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("tab", { name: en["speakingUx.adjudication"] }));
  fireEvent.change(screen.getByLabelText("Adjudicated Overall Band"), { target: { value: "6.5" } });
  expect(dirty).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("tab", { name: en["speakingUx.assignments"] }));
  fireEvent.click(screen.getByRole("tab", { name: en["speakingUx.adjudication"] }));
  expect(screen.getByLabelText("Adjudicated Overall Band")).toHaveValue(6.5);
  fireEvent.click(screen.getByLabelText(/Fictional reviewer —/));
  fireEvent.change(screen.getByLabelText(en["speakingHuman.rationale"]), { target: { value: "Independent consensus" } });
  fireEvent.click(screen.getByRole("button", { name: en["speakingHuman.adjudicateAction"] }));
  await waitFor(() => expect(human.adjudicate).toHaveBeenCalledWith(labSample.id, expect.objectContaining({ review_revision: 1, expected_revision: 0, assessment_ids: [assessment.id], bands, rationale: "Independent consensus", policy_version: "human-adjudication-v1" })));
  await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(false));
  expect(screen.getByLabelText("Adjudicated Overall Band")).toHaveValue(null);
});

it("preserves rater drafts when hiding the creation form", async () => {
  renderWithLocale(<HumanAdjudicationPanel sampleId={labSample.id} reviewRevision={1} />);
  await waitFor(() => expect(human.listRaters).toHaveBeenCalled());
  fireEvent.click(screen.getAllByRole("button", { name: en["speakingHuman.createRater"] })[0]);
  fireEvent.change(screen.getByLabelText(en["speakingHuman.displayName"]), { target: { value: "Unsaved reviewer" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getAllByRole("button", { name: en["speakingHuman.createRater"] })[0]);
  expect(screen.getByLabelText(en["speakingHuman.displayName"])).toHaveValue("Unsaved reviewer");
});

it("creates a frozen suite with the selected source revision and explicit holdout consent", async () => {
  renderWithLocale(<SuiteManager />);
  await screen.findByText(suite.name);
  fireEvent.click(screen.getByLabelText(en["speakingUx.inspectionConsent"]));
  fireEvent.click(screen.getByRole("button", { name: en["speakingSuites.new"] }));
  fireEvent.change(screen.getByLabelText(en["speakingSuites.name"]), { target: { value: "Fictional release suite" } });
  fireEvent.click(screen.getByLabelText(/DEV-051/));
  fireEvent.click(screen.getByLabelText(en["speakingSuites.holdoutEvaluation"]));
  expect(screen.getByRole("button", { name: "Create frozen suite" })).toBeDisabled();
  fireEvent.click(screen.getAllByLabelText(en["speakingSuites.holdoutConsent"])[0]);
  fireEvent.click(screen.getByRole("button", { name: "Create frozen suite" }));
  await waitFor(() => expect(quality.createSuite).toHaveBeenCalledWith(expect.objectContaining({ expected_revision: 0, holdout_evaluation: true, cohort: [{ sample_id: labSample.id, review_revision: 1 }], label_selection: { kind: "ADJUDICATED" } })));
});

it("creates a gate without changing its result selectors or policy", async () => {
  renderWithLocale(<GateManager />);
  fireEvent.click(screen.getByRole("button", { name: en["speakingGates.new"] }));
  await screen.findByRole("option", { name: /Fictional DEV suite/ });
  fireEvent.change(screen.getByLabelText(en["speakingGates.name"]), { target: { value: gate.name } });
  for (const [name, fingerprint] of [["Baseline", "a"], ["Candidate", "b"]]) {
    fireEvent.change(within(screen.getByRole("group", { name })).getByLabelText(/Configuration fingerprint/), { target: { value: fingerprint.repeat(64) } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Create gate" }));
  await waitFor(() => expect(quality.createGate).toHaveBeenCalledWith({ name: gate.name, suite_id: suite.id, baseline: gate.baseline, candidate: gate.candidate, policy: gate.policy }));
});

it.each(["INCONCLUSIVE", "INVALID"] as const)("keeps %s distinct from failure and does not fabricate missing counts", status => {
  renderWithLocale(<GateReport selectedReport={{ id: "report", gate_id: gate.id, status, protocol: gate.policy.protocol, fingerprint: "d".repeat(64), created_at: labSample.created_at, report: { matched_samples: 0, reasons: ["INSUFFICIENT_MATCHED_INDEPENDENT_CANDIDATES"], metrics: [{ metric: "wer", status, baseline: null, candidate: null, difference: null }] } }} />);
  expect(screen.getAllByText(status)).toHaveLength(2);
  expect(screen.getByText("Matched recordings").parentElement).toHaveTextContent("0");
  expect(screen.getByText("Unknown Billing Attempts").parentElement).toHaveTextContent("—");
  expect(screen.getByText("INSUFFICIENT_MATCHED_INDEPENDENT_CANDIDATES")).toBeVisible();
});

it("filters quality issues while leaving release blockers available", async () => {
  vi.mocked(quality.evaluateQuality).mockResolvedValue({ protocol: "speaking-dataset-quality-v1", evaluated_at: labSample.created_at, status: "BLOCKED", issues: [{ severity: "BLOCKED", code: "SOURCE", artifact: "sample", artifact_id: labSample.id, remediation: "Review the source." }, { severity: "NEEDS_REVIEW", code: "LABEL", artifact: "label", artifact_id: "label", remediation: "Verify the human label." }], samples: [], issue_counts: {}, eligible_samples: 0, ineligible_samples: 1, independent_candidates: 1, fingerprint: "a".repeat(64) });
  renderWithLocale(<QualityDashboard />);
  fireEvent.click(screen.getByRole("button", { name: "Run Quality Audit" }));
  await screen.findByText("Review the source.");
  fireEvent.change(screen.getByLabelText("Issue severity"), { target: { value: "BLOCKED" } });
  expect(screen.queryByText("Verify the human label.")).not.toBeInTheDocument();
  expect(screen.getByText("Review the source.")).toBeVisible();
});
