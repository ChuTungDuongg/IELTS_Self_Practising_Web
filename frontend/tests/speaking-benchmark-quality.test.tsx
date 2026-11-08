import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import * as qualityApi from "@/lib/api/speaking-benchmark-quality";
import * as humanApi from "@/lib/api/speaking-benchmark-human";
import * as questionsApi from "@/lib/api/speaking-benchmark-questions";
import { QuestionAssistant } from "@/features/speaking-benchmark/question-assistant";
import { BlindReviewer } from "@/features/speaking-benchmark/blind-reviewer";
import { QualityDashboard } from "@/features/speaking-benchmark/quality/quality-dashboard";
import { GateManager } from "@/features/speaking-benchmark/quality/gate-manager";

vi.mock("@/lib/api/speaking-benchmark-questions", async (original) => ({
  ...(await original<typeof questionsApi>()),
  questionJobs: vi.fn(),
  createQuestionJob: vi.fn(),
  prepareQuestions: vi.fn(),
  startQuestions: vi.fn(),
  decideQuestions: vi.fn(),
  cancelQuestions: vi.fn(),
}));

vi.mock("@/lib/api/speaking-benchmark-human", async (original) => ({
  ...(await original<typeof humanApi>()),
  blindAssignment: vi.fn(),
  submitBlindAssessment: vi.fn(),
  listRaters: vi.fn(),
  listAssignments: vi.fn(),
  listAssessments: vi.fn(),
  listAdjudications: vi.fn(),
  humanAgreement: vi.fn(),
}));

vi.mock("@/lib/api/speaking-benchmark-quality", async (original) => ({
  ...(await original<typeof qualityApi>()),
  evaluateQuality: vi.fn(),
  saveQualitySnapshot: vi.fn(),
  qualitySnapshots: vi.fn(),
  listSuites: vi.fn(),
  listGates: vi.fn(),
  createGate: vi.fn(),
  evaluateGate: vi.fn(),
  gateReports: vi.fn(),
}));

vi.mock("@/lib/api/speaking-benchmark", () => ({
  listSpeakingSamples: vi.fn().mockResolvedValue({
    items: [
      {
        id: "sample-1",
        code: "SAMP-001",
        split: "DEV",
        status: "APPROVED",
        duration_ms: 60000,
        review_revision: 2,
        label_status: "HUMAN_VERIFIED",
      },
    ],
    total: 1,
  }),
}));

describe("Speaking P4 boundaries & schemas", () => {
  it("requires an exact persisted artifact selector", () => {
    expect(
      qualityApi.persistedSelectionSchema.safeParse({
        kind: "EXPERIMENT",
        id: "10000000-0000-4000-8000-000000000051",
      }).success
    ).toBe(false);
    expect(
      qualityApi.persistedSelectionSchema.safeParse({
        kind: "GRADING",
        configuration_fingerprint: "a".repeat(64),
      }).success
    ).toBe(true);
  });

  it("rejects duplicate thresholds and fabricated IELTS bands", () => {
    expect(
      qualityApi.gatePolicySchema.safeParse({
        thresholds: [
          { metric: "wer", max_regression: 0 },
          { metric: "wer", max_regression: 0 },
        ],
      }).success
    ).toBe(false);
    expect(
      humanApi.bandsSchema.safeParse({
        fc: 6.2,
        lr: null,
        gra: null,
        pr: null,
        overall: null,
      }).success
    ).toBe(false);
    expect(
      humanApi.bandsSchema.parse({
        fc: 6.5,
        lr: null,
        gra: null,
        pr: null,
        overall: 7,
      }).overall
    ).toBe(7);
  });

  it("rejects aggregate/model data in the blind reviewer DTO", () => {
    const value = {
      id: "a",
      sample_id: "s",
      review_revision: 1,
      source_sha256: "a",
      manifest_fingerprint: "b",
      revision: 1,
      duration_ms: 1000,
      audio_url: "/audio",
      questions: [],
      assessments: [],
      created_at: "2026-11-08",
      predictions: [],
    };
    expect(humanApi.blindAssessmentSchema.safeParse(value).success).toBe(false);
  });
});

describe("QuestionAssistant UI", () => {
  const proposal: questionsApi.QuestionProposal = {
    id: "prop-1",
    source_review_revision: 1,
    source_sha256: "a".repeat(64),
    draft_fingerprint: "b".repeat(64),
    examiner_speaker_id: "SPEAKER_00",
    window_id: "w-1",
    start_ms: 2000,
    end_ms: 6000,
    recognized_text: "Could you tell me your full name, please?",
    provider_identity: { provider: "azure_stt" },
    candidate_segment_id: null,
    part_number: 1,
    question_type: "question",
    ambiguity_flags: ["MULTIPLE_TURNS"],
    human_verification_status: "PENDING",
  };

  const sampleJob: questionsApi.QuestionJob = {
    id: "job-1",
    sample_id: "sample-1",
    review_revision: 1,
    source_sha256: "a".repeat(64),
    draft_fingerprint: "b".repeat(64),
    model_fingerprint: "c".repeat(64),
    examiner_speaker_id: "SPEAKER_00",
    configuration: {},
    fingerprint: "d".repeat(64),
    windows: [],
    exclusions: [],
    status: "COMPLETED",
    error_code: null,
    proposals: [proposal],
    decisions: [],
    requests: [],
    created_at: "2026-11-08T00:00:00Z",
    started_at: "2026-11-08T00:00:01Z",
    finished_at: "2026-11-08T00:00:05Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(questionsApi.questionJobs).mockResolvedValue([sampleJob]);
  });

  it("sends an explicit provider estimate with start consent", async () => {
    const draft = { ...sampleJob, status: 'DRAFT', proposals: [] };
    vi.mocked(questionsApi.questionJobs).mockResolvedValue([draft]);
    vi.mocked(questionsApi.prepareQuestions).mockResolvedValue({preflight_fingerprint: draft.fingerprint,can_start:true,blockers:[],windows:[],exclusions:[],requests:{azure_stt:1},provider_audio_seconds:4,limits:{},warnings:[]});
    vi.mocked(questionsApi.startQuestions).mockResolvedValue({...draft,status:'PENDING'});
    renderWithLocale(<QuestionAssistant sampleId="sample-1" reviewRevision={1} />);
    fireEvent.click(await screen.findByRole('button', {name:'Preflight estimation'}));
    fireEvent.change(await screen.findByLabelText('Provider estimate (USD)'), {target:{value:'.2'}});
    fireEvent.change(screen.getByLabelText('Maximum estimated total (USD)'), {target:{value:'.5'}});
    fireEvent.click(screen.getByLabelText('I authorize audio submission to the selected provider.'));
    fireEvent.click(screen.getByRole('button',{name:'Authorize & extract questions'}));
    await waitFor(() => expect(questionsApi.startQuestions).toHaveBeenCalledWith('sample-1',draft.id,draft.fingerprint,expect.objectContaining({estimates_usd:{azure_stt:.2},max_estimated_cost_usd:.5})));
  });

  it("requires examiner confirmation before extracting questions", async () => {
    renderWithLocale(
      <QuestionAssistant sampleId="sample-1" reviewRevision={1} />
    );

    const extractBtn = screen.getByRole("button", {
      name: /analyze examiner turns/i,
    });
    expect(extractBtn).toBeDisabled();

    const checkbox = screen.getByLabelText(/corresponds to the examiner/i);
    fireEvent.click(checkbox);
    expect(extractBtn).not.toBeDisabled();
  });

  it("renders proposals and enables proposal decision recording", async () => {
    const onDraftUpdated = vi.fn();
    vi.mocked(questionsApi.decideQuestions).mockResolvedValue({
      ...sampleJob,
      decisions: [{ proposal_id: "prop-1", action: "ACCEPT" }],
    });

    renderWithLocale(
      <QuestionAssistant
        sampleId="sample-1"
        reviewRevision={1}
        onDraftUpdated={onDraftUpdated}
      />
    );

    await screen.findByDisplayValue("Could you tell me your full name, please?");
    expect(screen.getByText("MULTIPLE_TURNS")).toBeInTheDocument();

    const acceptBtn = screen.getByRole("button", { name: /accept proposal/i });
    fireEvent.click(acceptBtn);

    await waitFor(() => expect(questionsApi.decideQuestions).toHaveBeenCalled());
    expect(onDraftUpdated).toHaveBeenCalled();
  });
});

describe("BlindReviewer UI", () => {
  const blindAssignmentData: humanApi.BlindAssessment = {
    id: "assign-12345678",
    sample_id: "sample-1",
    review_revision: 1,
    source_sha256: "a".repeat(64),
    manifest_fingerprint: "b".repeat(64),
    revision: 1,
    duration_ms: 120000,
    audio_url: "/admin/speaking-benchmark/reviewer-assignments/assign-12345678/audio",
    questions: [
      {
        id: "q-1",
        part_number: 1,
        prompt_type: "general",
        prompt_text: "Do you work or study?",
        cue_points: [],
        start_ms: 1000,
        end_ms: 5000,
      },
    ],
    assessments: [],
    created_at: "2026-11-08T00:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(humanApi.blindAssignment).mockResolvedValue(blindAssignmentData);
  });

  it("enforces independent attestation before allowing submission", async () => {
    renderWithLocale(<BlindReviewer assignmentId="assign-12345678" />);

    await screen.findByText("Do you work or study?");
    const submitBtn = screen.getByRole("button", {
      name: /submit independent assessment/i,
    });
    expect(submitBtn).toBeDisabled();

    const attestCheck = screen.getByLabelText(
      /evaluated this recording independently without external assistance/i
    );
    fireEvent.click(attestCheck);
    expect(submitBtn).not.toBeDisabled();
  });

  it("submits scoring bands and displays read-only view", async () => {
    const submittedAssessment: humanApi.HumanAssessment = {
      id: "ass-1",
      assignment_id: "assign-12345678",
      sample_id: "sample-1",
      rater_id: "rater-1",
      review_revision: 1,
      source_sha256: "a".repeat(64),
      manifest_fingerprint: "b".repeat(64),
      revision: 1,
      status: "SUBMITTED",
      bands: { fc: 6.5, lr: 7.0, gra: 6.0, pr: 6.5, overall: 6.5 },
      comments: { fc: "Good flow", lr: "Rich vocabulary", gra: "Minor slips", pr: "Clear", overall: "Solid B2" },
      independently_performed: true,
      provenance: "external_unverified",
      source_reference: "blind-reviewer-assign-12345678",
      eligible: true,
      authored_by: "user-1",
      submitted_at: "2026-11-08T01:00:00Z",
    };

    vi.mocked(humanApi.submitBlindAssessment).mockResolvedValue(submittedAssessment);
    vi.mocked(humanApi.blindAssignment)
      .mockResolvedValueOnce(blindAssignmentData)
      .mockResolvedValueOnce({
        ...blindAssignmentData,
        assessments: [submittedAssessment],
      });

    renderWithLocale(<BlindReviewer assignmentId="assign-12345678" />);

    await screen.findByText("Do you work or study?");
    const attestCheck = screen.getByLabelText(/without external assistance/i);
    fireEvent.click(attestCheck);

    const submitBtn = screen.getByRole("button", {
      name: /submit independent assessment/i,
    });
    fireEvent.click(submitBtn);

    await waitFor(() =>
      expect(humanApi.submitBlindAssessment).toHaveBeenCalledWith(
        "assign-12345678",
        expect.objectContaining({
          independently_performed: true,
          expected_revision: 0,
          bands: expect.objectContaining({ fc: null, overall: null }),
        })
      )
    );
  });
});

describe("QualityDashboard UI", () => {
  const mockQualityReport: qualityApi.QualityReport = {
    protocol: "speaking-dataset-quality-v1",
    evaluated_at: "2026-11-08T00:00:00Z",
    status: "READY",
    issues: [],
    samples: [],
    issue_counts: {},
    eligible_samples: 1,
    ineligible_samples: 0,
    independent_candidates: 1,
    fingerprint: "q".repeat(64),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(qualityApi.qualitySnapshots).mockResolvedValue([]);
    vi.mocked(qualityApi.evaluateQuality).mockResolvedValue(mockQualityReport);
  });

  it("renders quality audit and triggers evaluation", async () => {
    renderWithLocale(<QualityDashboard />);

    await screen.findByText("Protocol: speaking-dataset-quality-v1");
    const evalBtn = screen.getByRole("button", {
      name: /run quality audit/i,
    });
    fireEvent.click(evalBtn);

    await waitFor(() => expect(qualityApi.evaluateQuality).toHaveBeenCalled());
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByText("Eligible Samples")).toBeInTheDocument();
  });
});

describe("GateManager UI", () => {
  const mockGate: qualityApi.RegressionGate = {
    id: "gate-1",
    name: "Production Accuracy Gate",
    suite_id: "suite-1",
    baseline: { kind: "GRADING", configuration_fingerprint: "0".repeat(64) },
    candidate: { kind: "GRADING", configuration_fingerprint: "1".repeat(64) },
    policy: {
      protocol: "speaking-regression-gate-v1",
      comparison: "CONFIGURATION",
      minimum_independent_candidates: 1,
      minimum_prediction_coverage: 1.0,
      minimum_reference_coverage: 1.0,
      thresholds: [{ metric: "wer", max_regression: 0.0 }],
      max_unknown_billing_attempts: 0,
    },
    fingerprint: "g".repeat(64),
    created_at: "2026-11-08T00:00:00Z",
  };

  const mockReport: qualityApi.RegressionReport = {
    id: "rep-1",
    gate_id: "gate-1",
    status: "PASS",
    protocol: "speaking-regression-gate-v1",
    fingerprint: "r".repeat(64),
    report: {
      candidate_unknown_billing_requests: 0,
      metrics: [
        {
          metric: "wer",
          baseline: 0.12,
          candidate: 0.11,
          difference: -0.01,
          relative_difference: -0.0833,
          tolerable_regression: 0.0,
          status: "PASS",
          paired: { ci95: [-0.02, 0.0] },
        },
      ],
    },
    created_at: "2026-11-08T00:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(qualityApi.listGates).mockResolvedValue([mockGate]);
    vi.mocked(qualityApi.listSuites).mockResolvedValue([]);
    vi.mocked(qualityApi.gateReports).mockResolvedValue([mockReport]);
  });

  it("renders gate details and evaluation report comparison table", async () => {
    renderWithLocale(<GateManager />);

    await screen.findByText("Production Accuracy Gate");
    const selectBtn = screen.getByRole("button", { name: /select gate/i });
    fireEvent.click(selectBtn);

    await screen.findAllByText("PASS");
    expect(screen.getByText("0.1200")).toBeInTheDocument();
    expect(screen.getByText("0.1100")).toBeInTheDocument();
    expect(screen.getByText("-0.0100")).toBeInTheDocument();
    expect(screen.getByText("[-0.020, 0.000]")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /export csv/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/export.csv")
    );
  });
});
