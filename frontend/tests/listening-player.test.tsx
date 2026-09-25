import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListeningAudioPlayer } from "@/features/listening/audio-player";
import { listeningQuestionTypeOptions, questionRegistry } from "@/features/questions/registry";
import { ListeningBuilder } from "@/features/test-builder/listening-builder";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { BuilderAutosaveStatus, BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { ApiError } from "@/lib/api/client";
import { createListeningQuestionGroup, updateListeningPart, updateListeningQuestionGroup, type BuilderQuestionGroup, type BuilderVersion } from "@/lib/api/builder";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, recordActivity: vi.fn(), saveAnswer: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
});
vi.mock("@/lib/api/builder", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/builder")>();
  return { ...actual, createListeningQuestionGroup: vi.fn(), updateListeningQuestionGroup: vi.fn(), updateListeningPart: vi.fn() };
});

function listeningBuilderVersion(questionGroups: BuilderQuestionGroup[]): BuilderVersion {
  return {
    id: crypto.randomUUID(),
    test_id: crypto.randomUUID(),
    test_title: "Practice",
    version_number: 1,
    status: "DRAFT",
    modules: [{
      id: crypto.randomUUID(),
      revision: 1,
      module_type: "LISTENING",
      title: "Listening",
      recommended_duration_seconds: 1800,
      audio_asset: null,
      passages: [],
      listening_parts: Array.from({ length: 4 }, (_, index) => ({
        id: crypto.randomUUID(),
        revision: 1,
        title: `Section ${index + 1}`,
        order_index: index,
        question_groups: index === 0 ? questionGroups : [],
      })),
      writing_tasks: [],
    }],
  };
}

describe("Listening audio and templates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
    Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: vi.fn() });
  });
  afterEach(() => vi.useRealTimers());

  it("offers required practice playback speeds and updates playbackRate", () => {
    const { container } = render(<ListeningAudioPlayer src="/part-1.mp3" />);
    const speed = screen.getByLabelText("Playback speed") as HTMLSelectElement;
    expect([...speed.options].map((option) => option.text)).toEqual(expect.arrayContaining(["1.25x", "1.5x", "2x"]));
    fireEvent.change(speed, { target: { value: "1.5" } });
    expect((container.querySelector("audio") as HTMLAudioElement).playbackRate).toBe(1.5);
  });

  it("seeks freely in practice policy", () => {
    const { container } = render(<ListeningAudioPlayer src="/part-1.mp3" />);
    const audio = container.querySelector("audio") as HTMLAudioElement;
    Object.defineProperty(audio, "duration", { configurable: true, value: 120 });
    fireEvent.loadedMetadata(audio);
    fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "42" } });
    expect(audio.currentTime).toBe(42);
  });

  it("loads a new source without leaving the previous part playing", () => {
    const view = render(<ListeningAudioPlayer src="/part-1.mp3" />);
    const audio = view.container.querySelector("audio") as HTMLAudioElement;
    view.rerender(<ListeningAudioPlayer src="/part-2.mp3" />);
    expect(audio.src).toMatch(/part-2\.mp3$/);
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalled();
  });

  it("registers every practical Listening template", () => {
    const ids = listeningQuestionTypeOptions.map((item) => item.id);
    expect(ids).toEqual(expect.arrayContaining(["multiple_choice", "multiple_choice_multiple", "matching", "plan_labelling", "map_labelling", "diagram_labelling", "form_completion", "note_completion", "table_completion", "flow_chart_completion", "summary_completion", "sentence_completion", "short_answer"]));
    expect(questionRegistry.map_labelling.createDefault(11).questions[0].number).toBe(11);
  });

  it("opens all four stable sections with one optional shared audio", () => {
    const version = { id: crypto.randomUUID(), test_id: crypto.randomUUID(), test_title: "Practice", version_number: 1, status: "DRAFT", modules: [{ id: crypto.randomUUID(), revision: 1, module_type: "LISTENING", title: "Listening", recommended_duration_seconds: 1800, audio_asset: null, passages: [], listening_parts: Array.from({ length: 4 }, (_, index) => ({ id: crypto.randomUUID(), revision: 1, title: `Section ${index + 1}`, order_index: index, question_groups: [] })), writing_tasks: [] }] } as BuilderVersion;
    render(<BuilderLifecycleProvider><ListeningBuilder version={version} /></BuilderLifecycleProvider>);
    expect(screen.getByRole("tab", { name: /Section 1/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("No recording attached")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Section 2/ }));
    expect(screen.getByText("No recording attached")).toBeInTheDocument();
    expect(screen.getAllByText(/Shared Listening audio/)).toHaveLength(1);
  });

  it("shows and edits the full range for one shared multi select group in the Builder", async () => {
    const persisted = {
      ...questionRegistry.multiple_choice_multiple.createDefault(13),
      id: crypto.randomUUID(), revision: 1, image_asset_id: null, image_asset: null,
    } as BuilderQuestionGroup;
    render(<BuilderLifecycleProvider><ListeningBuilder version={listeningBuilderVersion([persisted])} /></BuilderLifecycleProvider>);
    expect(screen.getByText("Q13–14")).toBeInTheDocument();
    expect(screen.getByText("2 / 40 questions")).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit" })); await Promise.resolve(); });
    expect(screen.getByRole("combobox", { name: "Required selections" })).toHaveValue("2");
    fireEvent.change(screen.getByRole("combobox", { name: "Required selections" }), { target: { value: "3" } });
    expect(screen.getByText("Q13–15")).toBeInTheDocument();
  });

  it("autosaves an existing Listening group through UPDATE without creating a duplicate", async () => {
    vi.useFakeTimers();
    const persisted = {
      ...questionRegistry.multiple_choice.createDefault(1),
      id: crypto.randomUUID(),
      revision: 1,
      image_asset_id: null,
      image_asset: null,
    } as BuilderQuestionGroup;
    vi.mocked(updateListeningQuestionGroup).mockResolvedValue(persisted);
    render(<BuilderLifecycleProvider><ListeningBuilder version={listeningBuilderVersion([persisted])} /></BuilderLifecycleProvider>);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Edit" }));
      await Promise.resolve();
    });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Latest persisted prompt" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    expect(updateListeningQuestionGroup).toHaveBeenCalledTimes(1);
    expect(updateListeningQuestionGroup).toHaveBeenCalledWith(
      persisted.id,
      expect.objectContaining({ questions: [expect.objectContaining({ prompt: "Latest persisted prompt" })] }),
      1,
    );
    expect(createListeningQuestionGroup).not.toHaveBeenCalled();
  });

  it("uses acknowledged revisions for repeated Listening group autosaves", async () => {
    vi.useFakeTimers();
    const persisted = { ...questionRegistry.multiple_choice.createDefault(1), id: crypto.randomUUID(), revision: 5, image_asset_id: null, image_asset: null } as BuilderQuestionGroup;
    vi.mocked(updateListeningQuestionGroup)
      .mockResolvedValueOnce({ ...persisted, revision: 6 })
      .mockResolvedValueOnce({ ...persisted, revision: 7 });
    render(<BuilderLifecycleProvider><ListeningBuilder version={listeningBuilderVersion([persisted])} /></BuilderLifecycleProvider>);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit" })); await Promise.resolve(); });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "First edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Second edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(vi.mocked(updateListeningQuestionGroup).mock.calls.map(([, , expected]) => expected)).toEqual([5, 6]);
  });

  it("stops Listening group autosave after a stale conflict", async () => {
    vi.useFakeTimers();
    const persisted = { ...questionRegistry.multiple_choice.createDefault(1), id: crypto.randomUUID(), revision: 5, image_asset_id: null, image_asset: null } as BuilderQuestionGroup;
    vi.mocked(updateListeningQuestionGroup).mockRejectedValue(new ApiError("DRAFT_REVISION_CONFLICT", "Reload latest", 409));
    render(<BuilderLifecycleProvider><ListeningBuilder version={listeningBuilderVersion([persisted])} /><BuilderAutosaveStatus /></BuilderLifecycleProvider>);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Edit" })); await Promise.resolve(); });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Stale edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByRole("button", { name: "Reload latest" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "More stale edits" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(updateListeningQuestionGroup).toHaveBeenCalledTimes(1);
  });

  it("uses acknowledged revisions for repeated Listening part title autosaves", async () => {
    vi.useFakeTimers();
    const value = listeningBuilderVersion([]);
    const part = value.modules[0].listening_parts[0];
    part.revision = 4;
    vi.mocked(updateListeningPart)
      .mockResolvedValueOnce({ ...part, title: "First title", revision: 5 })
      .mockResolvedValueOnce({ ...part, title: "Second title", revision: 6 });
    render(<BuilderLifecycleProvider><ListeningBuilder version={value} /></BuilderLifecycleProvider>);
    fireEvent.change(screen.getByLabelText("Section title / internal label"), { target: { value: "First title" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Section title / internal label"), { target: { value: "Second title" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(vi.mocked(updateListeningPart).mock.calls.map(([, body]) => body.expected_revision)).toEqual([4, 5]);
  });

  it("switches persisted group editors without carrying the previous group's local draft", async () => {
    const first = {
      ...questionRegistry.multiple_choice.createDefault(1),
      id: crypto.randomUUID(),
      image_asset_id: null,
      image_asset: null,
    } as BuilderQuestionGroup;
    first.questions[0].prompt = "First group prompt";
    const second = {
      ...questionRegistry.multiple_choice.createDefault(2),
      id: crypto.randomUUID(),
      order_index: 1,
      image_asset_id: null,
      image_asset: null,
    } as BuilderQuestionGroup;
    second.questions[0].prompt = "Second group prompt";
    render(<BuilderLifecycleProvider><ListeningBuilder version={listeningBuilderVersion([first, second])} /></BuilderLifecycleProvider>);

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Prompt")).toHaveValue("First group prompt");

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]);
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Prompt")).toHaveValue("Second group prompt");
  });

  it("creates a new Listening group with one POST and waits for server identity", async () => {
    const version = listeningBuilderVersion([]);
    const created = {
      ...questionRegistry.multiple_choice.createDefault(1),
      id: crypto.randomUUID(),
      image_asset_id: null,
      image_asset: null,
    } as BuilderQuestionGroup;
    vi.mocked(createListeningQuestionGroup).mockResolvedValue(created);
    render(<BuilderLifecycleProvider><ListeningBuilder version={version} /></BuilderLifecycleProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Add question group" }));
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Edited before first save" } });
    fireEvent.click(screen.getByRole("button", { name: "Save group" }));

    await waitFor(() => expect(createListeningQuestionGroup).toHaveBeenCalledTimes(1));
    expect(createListeningQuestionGroup).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ questions: [expect.objectContaining({ prompt: "Edited before first save" })] }),
    );
    expect(updateListeningQuestionGroup).not.toHaveBeenCalled();
  });

  it("mounts one shared player while navigating Listening sections", () => {
    const audio = { id: crypto.randomUUID(), original_name: "shared.mp3", mime_type: "audio/mpeg", file_size: 1000, content_url: "/assets/shared/content" };
    const initial = {
      attempt: { attempt_id: crypto.randomUUID(), test_version_id: crypto.randomUUID(), module: "LISTENING", status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: new Date().toISOString(), paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: new Date().toISOString(), finished_at: null, elapsed_seconds: 0, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: new Date().toISOString() },
      test_title: "Practice",
      passages: [], highlights: [], listening_audio_asset: audio,
      listening_parts: Array.from({ length: 4 }, (_, index) => ({ id: crypto.randomUUID(), title: `Section ${index + 1}`, order_index: index, question_groups: [] })),
    } as unknown as import("@/lib/api/exam").ExamPayload;
    render(<ListeningRunner initial={initial} />);
    expect(screen.getByRole("button", { name: "Pause & exit" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("Listening audio player")).toHaveLength(1);
    const loadsAfterMount = vi.mocked(HTMLMediaElement.prototype.load).mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Section 2" }));

    expect(screen.getAllByLabelText("Listening audio player")).toHaveLength(1);
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalledTimes(loadsAfterMount);
  });

  it("renders Listening review answers with semantic result styles", () => {
    const questionId = crypto.randomUUID();
    const data = {
      review: {
        attempt: { raw_score: 35, max_score: 40, band_score: 8.0 },
        test_title: "Practice",
        answers: [{ question_id: questionId, value: "TRUE", is_correct: true }],
      },
      audio_asset: null,
      parts: [{
        id: crypto.randomUUID(), title: "Section 1", order_index: 0,
        question_groups: [{
          id: crypto.randomUUID(), question_type: "true_false_not_given", instruction: "", config: {}, order_index: 0,
          questions: [{ id: questionId, number: 1, prompt: "Statement", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, explanation: "Supported by the recording.", order_index: 0 }],
        }],
      }],
    };

    const view = render(<ListeningReviewView data={data as never} />);

    expect(screen.getByText("Listening review")).toBeInTheDocument();
    expect(screen.getByText("35 / 40")).toBeInTheDocument();
    expect(screen.getByText("Band 8.0")).toBeInTheDocument();
    expect(screen.getByText("Your answer: TRUE")).toBeInTheDocument();
    expect(view.container.querySelector(".review-answer-correct")).toBeInTheDocument();
  });
});
