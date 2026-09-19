import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ListeningAudioPlayer } from "@/features/listening/audio-player";
import { listeningQuestionTypeOptions, questionRegistry } from "@/features/questions/registry";
import { ListeningBuilder } from "@/features/test-builder/listening-builder";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import type { BuilderVersion } from "@/lib/api/builder";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

describe("Listening audio and templates", () => {
  beforeEach(() => {
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

  it("navigates stable Part 1–4 records and shows each audio attachment", () => {
    const version = { id: crypto.randomUUID(), test_id: crypto.randomUUID(), test_title: "Practice", version_number: 1, status: "DRAFT", modules: [{ id: crypto.randomUUID(), module_type: "LISTENING", title: "Listening", recommended_duration_seconds: 1800, passages: [], listening_parts: Array.from({ length: 4 }, (_, index) => ({ id: crypto.randomUUID(), title: `Part ${index + 1}`, order_index: index, audio_asset: { id: crypto.randomUUID(), original_name: `part-${index + 1}.mp3`, mime_type: "audio/mpeg", file_size: 1000, content_url: `/assets/${index}/content` }, question_groups: [] })) }] } as BuilderVersion;
    render(<BuilderLifecycleProvider><ListeningBuilder version={version} /></BuilderLifecycleProvider>);
    expect(screen.getByRole("tab", { name: /Part 1/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: /Part 2/ }));
    expect(screen.getByText("part-2.mp3")).toBeInTheDocument();
  });
});
