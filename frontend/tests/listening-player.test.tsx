import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ListeningAudioPlayer } from "@/features/listening/audio-player";
import { listeningQuestionTypeOptions, questionRegistry } from "@/features/questions/registry";
import { ListeningBuilder } from "@/features/test-builder/listening-builder";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import type { BuilderVersion } from "@/lib/api/builder";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, recordActivity: vi.fn(), saveAnswer: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, getExam: vi.fn(), saveFlag: vi.fn(), submitAttempt: vi.fn() };
});

describe("Listening audio and templates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
    Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: vi.fn() });
  });

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
    const version = { id: crypto.randomUUID(), test_id: crypto.randomUUID(), test_title: "Practice", version_number: 1, status: "DRAFT", modules: [{ id: crypto.randomUUID(), module_type: "LISTENING", title: "Listening", recommended_duration_seconds: 1800, audio_asset: null, passages: [], listening_parts: Array.from({ length: 4 }, (_, index) => ({ id: crypto.randomUUID(), title: `Section ${index + 1}`, order_index: index, question_groups: [] })), writing_tasks: [] }] } as BuilderVersion;
    render(<BuilderLifecycleProvider><ListeningBuilder version={version} /></BuilderLifecycleProvider>);
    expect(screen.getByRole("tab", { name: /Section 1/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("No recording attached")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Section 2/ }));
    expect(screen.getByText("No recording attached")).toBeInTheDocument();
    expect(screen.getAllByText(/Shared Listening audio/)).toHaveLength(1);
  });

  it("mounts one shared player while navigating Listening sections", () => {
    const audio = { id: crypto.randomUUID(), original_name: "shared.mp3", mime_type: "audio/mpeg", file_size: 1000, content_url: "/assets/shared/content" };
    const initial = {
      attempt: { attempt_id: crypto.randomUUID(), test_version_id: crypto.randomUUID(), module: "LISTENING", status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: new Date().toISOString(), deadline_at: null, last_active_at: new Date().toISOString(), finished_at: null, elapsed_seconds: 0, remaining_seconds: null, raw_score: null, max_score: null, server_time: new Date().toISOString() },
      test_title: "Practice",
      passages: [], highlights: [], listening_audio_asset: audio,
      listening_parts: Array.from({ length: 4 }, (_, index) => ({ id: crypto.randomUUID(), title: `Section ${index + 1}`, order_index: index, question_groups: [] })),
    } as unknown as import("@/lib/api/exam").ExamPayload;
    render(<ListeningRunner initial={initial} />);
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
