import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import * as api from "@/lib/api/speaking-benchmark-research";
import { ExperimentCreate } from "@/features/speaking-benchmark/research/experiment-create";
import { ExperimentControls } from "@/features/speaking-benchmark/research/experiment-controls";
import { ReferenceEditor } from "@/features/speaking-benchmark/research/reference-editor";
import { TranscriptComparison } from "@/features/speaking-benchmark/research/transcript-comparison";
import { ResearchDetail } from "@/features/speaking-benchmark/research/research-detail";

vi.mock("@/lib/api/speaking-benchmark-research", async original => ({ ...await original<typeof api>(), researchCohort: vi.fn(), referenceHistory: vi.fn(), saveReference: vi.fn(), verifyReference: vi.fn(), createExperiment: vi.fn(), prepareExperiment: vi.fn(), startExperiment: vi.fn(), cancelExperiment: vi.fn(), reconcileExperiment: vi.fn(), getExperiment: vi.fn(), experimentResults: vi.fn() }));

const cohort = { sample_id: "s", code: "Synthetic sample", candidate_id: "speaker-a", split: "DEV" as const, source_sha256: "a".repeat(64), review_revision: 2, manifest_fingerprint: "b".repeat(64), windows: [{ id: "response-a", part_number: 1, start_ms: 1000, end_ms: 4000 }] };
const config = { provider: "azure_pa", silence_ms: null, identity: { provider: "azure-speech" }, normalizer: {}, grading: null };
const experiment = api.experimentSchema.parse({ id: "exp", name: "Fictional ASR study", description: "", mode: "ASR_ONLY", configuration: { cohort: [cohort], variants: [{ ...config, key: "azure_pa" }], requests: { azure_pa: 1 }, provider_audio_ms: 3000, limits: { provider_audio_seconds: 120, physical_requests: 10 }, split_policy: "DEV" }, fingerprint: "c".repeat(64), evaluation_selection: {}, status: "DRAFT", created_at: "2026-11-08T00:00:00Z", started_at: null, finished_at: null, holdout_executed_at: null, variants: [{ id: "variant", sample_id: "s", review_revision: 2, provider_key: "azure_pa", configuration: config, fingerprint: "d".repeat(64), windows: cohort.windows, status: "PENDING", error_code: null, grading_run_id: null }] });
const report = api.researchReportSchema.parse({ schema_version: "admin-speaking-research-v1", experiment_id: "exp", status: "COMPLETED", mode: "ASR_ONLY", fingerprint: "c".repeat(64), reference_policy: "frozen", summary: { azure_pa: { samples: 1, human_labelled_samples: 0, micro_wer: null, macro_sample_wer: null, macro_speaker_wer: null, cer: null, reference_words: 0, missing_or_failed_results: 0, unavailable_accuracy_responses: 1, latency_mean_ms: 100, latency_p95_ms: 100, new_requests: 1, cache_hits: 0, missing_words: null, hallucinated_words: null } }, paired_asr: [], paired_bands: [], band_summary: {}, band_rows: [], disagreement: [], rows: [{ variant_id: "variant", sample_id: "s", code: cohort.code, candidate_id: "speaker-a", split: "DEV", segment_id: "response-a", review_revision: 2, part: 1, start_ms: 1000, end_ms: 4000, provider: "azure_pa", model_identity: {}, status: "COMPLETE", reference_revision: null, reference_status: "UNAVAILABLE", reference_text: null, text: "um I I yesterday go", latency_ms: 100, real_time_factor: .03, metrics: { truth: "UNAVAILABLE", wer: null, cer: null, reference_words: 0 }, coverage: null, words: [], diff: [] }], limitations: ["LIVE_ACCURACY_UNVERIFIED"], physical_requests: [], total: 1, offset: 0, limit: 25 });
const reference = api.referenceSchema.parse({ id: "ref", sample_id: "s", review_revision: 2, source_sha256: cohort.source_sha256, manifest_fingerprint: cohort.manifest_fingerprint, segment_id: "response-a", start_ms: 1000, end_ms: 4000, revision: 1, normalization: "asr-research-nfc-casefold-words-v2", text: "Yesterday I go", annotations: [], uncertainty: [], metadata_labels: {}, status: "DRAFT", provenance: "independent_human_transcriber", source_reference: "Fictional human transcriber", author_id: "owner", reviewer_id: null, verified_at: null, created_at: "2026-11-08T00:00:00Z" });

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(api.researchCohort).mockResolvedValue([cohort]); vi.mocked(api.referenceHistory).mockResolvedValue([]);
  vi.mocked(api.getExperiment).mockResolvedValue(experiment); vi.mocked(api.experimentResults).mockResolvedValue(report);
  vi.mocked(api.prepareExperiment).mockResolvedValue({ preflight_fingerprint: experiment.fingerprint, can_start: true, blockers: [], requests: { azure_pa: 1 }, provider_audio_seconds: 3, limits: {}, warnings: [] });
  vi.mocked(api.startExperiment).mockResolvedValue({ ...experiment, status: "PENDING" });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
});

it("freezes exact approved windows without starting any inference", async () => {
  const created = vi.fn(); vi.mocked(api.createExperiment).mockResolvedValue(experiment);
  renderWithLocale(<ExperimentCreate onCreated={created} />);
  await screen.findByText("Synthetic sample");
  fireEvent.change(screen.getByLabelText("Experiment name"), { target: { value: "Fictional study" } });
  fireEvent.click(screen.getByLabelText(/Part 1/)); fireEvent.click(screen.getByLabelText("azure_pa"));
  fireEvent.click(screen.getByRole("button", { name: "Freeze experiment" }));
  await waitFor(() => expect(created).toHaveBeenCalled());
  expect(api.createExperiment).toHaveBeenCalledWith(expect.objectContaining({ mode: "ASR_ONLY", cohort: [{ sample_id: "s", review_revision: 2, segment_ids: ["response-a"] }] }));
  expect(api.startExperiment).not.toHaveBeenCalled(); expect(api.prepareExperiment).not.toHaveBeenCalled();
});

it("saves learner grammar literally and verifies only an independently reviewed saved revision", async () => {
  vi.mocked(api.saveReference).mockResolvedValue(reference);
  vi.mocked(api.verifyReference).mockResolvedValue({ ...reference, revision: 2, status: "VERIFIED" });
  const play = vi.fn(); const dirty = vi.fn();
  renderWithLocale(<ReferenceEditor sampleId="s" reviewRevision={2} onPlay={play} onDirty={dirty} />);
  await screen.findByRole("option", { name: /r2/ });
  fireEvent.click(screen.getByRole("button", { name: "Play this window" })); expect(play).toHaveBeenCalledWith(1000, 4000);
  fireEvent.change(screen.getByLabelText("Human transcript"), { target: { value: "Yesterday I go" } });
  fireEvent.change(screen.getByLabelText("Transcriber / independent source reference"), { target: { value: "Fictional human transcriber" } });
  expect(screen.getByRole("button", { name: "Verify independent reference" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Save new revision" }));
  await waitFor(() => expect(api.saveReference).toHaveBeenCalledWith("s", expect.objectContaining({ text: "Yesterday I go", expected_revision: 0, start_ms: 1000, end_ms: 4000 })));
  await waitFor(() => expect(screen.getByLabelText("I independently reviewed this transcript against the audio.")).toBeEnabled());
  fireEvent.click(screen.getByLabelText("I independently reviewed this transcript against the audio."));
  fireEvent.click(screen.getByRole("button", { name: "Verify independent reference" }));
  await waitFor(() => expect(api.verifyReference).toHaveBeenCalledWith("s", reference));
  expect(dirty).toHaveBeenCalledWith(true); expect(dirty).toHaveBeenCalledWith(false);
});

it("requires preflight, per-provider estimates, audio consent and final confirmation", async () => {
  const changed = vi.fn(); renderWithLocale(<ExperimentControls experiment={experiment} report={report} onChanged={changed} />);
  expect(api.prepareExperiment).not.toHaveBeenCalled(); expect(api.startExperiment).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Check readiness and request budget" }));
  await screen.findByLabelText(/azure_pa · 1 requests/);
  expect(screen.getByRole("button", { name: "Authorize and start" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/azure_pa · 1 requests/), { target: { value: ".1" } });
  fireEvent.change(screen.getByLabelText("Accepted total estimate ceiling (USD)"), { target: { value: "1" } });
  fireEvent.click(screen.getByLabelText("I authorize audio submission to the selected providers."));
  fireEvent.click(screen.getByRole("button", { name: "Authorize and start" }));
  expect(api.startExperiment).not.toHaveBeenCalled();
  const dialog = screen.getByRole("dialog"); fireEvent.click(within(dialog).getByRole("button", { name: "Authorize and start" }));
  await waitFor(() => expect(api.startExperiment).toHaveBeenCalledWith("exp", experiment.fingerprint, expect.objectContaining({ estimates_usd: { azure_pa: .1 }, llm_text: false, modal_gpu: false })));
});

it("uses one authenticated source player and stops exactly at the response end", async () => {
  const { container } = renderWithLocale(<TranscriptComparison experiment={{ ...experiment, status: "COMPLETED" }} latest={false} />);
  await screen.findByText("um I I yesterday go"); expect(container.querySelectorAll("audio")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Play this window" }));
  const audio = container.querySelector("audio")!; expect(audio.currentTime).toBe(1);
  audio.currentTime = 4; fireEvent.timeUpdate(audio); expect(audio.pause).toHaveBeenCalled();
  expect(screen.getByText(/Verified human transcript unavailable/)).toBeInTheDocument();
  expect(api.experimentResults).toHaveBeenCalledWith("exp", expect.objectContaining({ sample_id: "s", segment_id: "response-a" }));
});

it("presents missing references honestly and filters exports without rerunning inference", async () => {
  renderWithLocale(<ResearchDetail experimentId="exp" initialFilters={{ split: "DEV" }} />);
  await screen.findByRole("heading", { name: "Fictional ASR study" });
  expect(screen.getAllByText(/Verified human transcript unavailable/).length).toBeGreaterThan(0);
  const exported = screen.getByRole("link", { name: "Export research metrics JSON" });
  expect(exported).toHaveAttribute("href", expect.stringContaining("split=DEV"));
  fireEvent.click(screen.getByLabelText(/Recalculate with latest verified references/));
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() => expect(api.experimentResults).toHaveBeenCalledWith("exp", expect.objectContaining({ latest_references: "true" }), 0));
  expect(api.startExperiment).not.toHaveBeenCalled(); expect(api.createExperiment).not.toHaveBeenCalled();
});

it("preserves precise uncertainty types and source spans when revising text", async () => {
  const uncertainty: api.ASRReference["uncertainty"] = [
    { start_ms: 1500, end_ms: 1700, kind: "unintelligible" },
    { start_ms: 2200, end_ms: 2400, kind: "questionable_reference" },
  ];
  vi.mocked(api.referenceHistory).mockResolvedValue([{ ...reference, uncertainty }]);
  vi.mocked(api.saveReference).mockResolvedValue({ ...reference, id: "ref-2", uncertainty, revision: 2 });
  renderWithLocale(<ReferenceEditor sampleId="s" reviewRevision={2} onPlay={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText("Human transcript")).toHaveValue(reference.text));
  fireEvent.change(screen.getByLabelText("Human transcript"), { target: { value: "um Yesterday I go" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new revision" }));
  await waitFor(() => expect(api.saveReference).toHaveBeenCalledWith("s", expect.objectContaining({ uncertainty, expected_revision: 1 })));
});

it("keeps editing disabled until the selected reference history has loaded", async () => {
  let finish!: (rows: api.ASRReference[]) => void;
  vi.mocked(api.referenceHistory).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  renderWithLocale(<ReferenceEditor sampleId="s" reviewRevision={2} onPlay={vi.fn()} />);
  await screen.findByRole("option", { name: /r2/ });
  expect(screen.getByLabelText("Human transcript")).toBeDisabled();
  finish([reference]);
  await waitFor(() => expect(screen.getByLabelText("Human transcript")).toBeEnabled());
  expect(screen.getByLabelText("Human transcript")).toHaveValue(reference.text);
});

it("edits uncertainty kind and boundaries with labelled controls", async () => {
  vi.mocked(api.referenceHistory).mockResolvedValue([reference]);
  vi.mocked(api.saveReference).mockResolvedValue({ ...reference, id: "ref-2", revision: 2 });
  renderWithLocale(<ReferenceEditor sampleId="s" reviewRevision={2} onPlay={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText("Human transcript")).toHaveValue(reference.text));
  fireEvent.click(screen.getByLabelText("Uncertain or unintelligible speech in this window"));
  fireEvent.change(screen.getByLabelText("Uncertainty kind"), { target: { value: "unintelligible" } });
  fireEvent.change(screen.getByLabelText("Start in source (ms)"), { target: { value: "1500" } });
  fireEvent.change(screen.getByLabelText("End in source (ms)"), { target: { value: "1700" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new revision" }));
  await waitFor(() => expect(api.saveReference).toHaveBeenCalledWith("s", expect.objectContaining({ uncertainty: [{ kind: "unintelligible", start_ms: 1500, end_ms: 1700 }] })));
});

it("keeps an unsaved transcript when the interface language changes", async () => {
  vi.mocked(api.referenceHistory).mockResolvedValue([reference]);
  renderWithLocale(<ReferenceEditor sampleId="s" reviewRevision={2} onPlay={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText("Human transcript")).toHaveValue(reference.text));
  fireEvent.change(screen.getByLabelText("Human transcript"), { target: { value: "um My unsaved verbatim words" } });
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  await waitFor(() => expect(screen.getByLabelText("Bản chép lời tham chiếu")).toHaveValue("um My unsaved verbatim words"));
  expect(api.referenceHistory).toHaveBeenCalledTimes(1);
});

it("blocks response switching while the next reference history is pending", async () => {
  vi.mocked(api.researchCohort).mockResolvedValue([{ ...cohort, windows: [...cohort.windows, { id: "response-b", part_number: 2, start_ms: 5000, end_ms: 8000 }] }]);
  let finish!: (rows: api.ASRReference[]) => void;
  vi.mocked(api.referenceHistory).mockResolvedValueOnce([reference]).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  renderWithLocale(<ReferenceEditor sampleId="s" reviewRevision={2} onPlay={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText("Human transcript")).toHaveValue(reference.text));
  const selector = screen.getByLabelText("Candidate response");
  fireEvent.change(selector, { target: { value: "2:response-b" } });
  expect(selector).toBeDisabled();
  expect(screen.getByLabelText("Human transcript")).toBeDisabled();
  finish([]);
  await waitFor(() => expect(selector).toBeEnabled());
  expect(screen.getByLabelText("Human transcript")).toHaveValue("");
});
