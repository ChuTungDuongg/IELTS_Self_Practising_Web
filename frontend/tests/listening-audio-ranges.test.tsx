import { act, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListeningAudioPlayer, type ListeningAudioPlayerHandle } from "@/features/listening/audio-player";
import { formatAudioTime, parseAudioTime } from "@/features/listening/audio-time";
import { ListeningSectionEditor } from "@/features/test-builder/listening-section-editor";
import { BuilderAutosaveStatus, BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { updateListeningPart, type BuilderListeningPart } from "@/lib/api/builder";
import { ApiError } from "@/lib/api/client";

vi.mock("@/lib/api/builder", () => ({ updateListeningPart: vi.fn() }));
const part: BuilderListeningPart = { id: crypto.randomUUID(), revision: 4, title: "Fictional section", order_index: 1, audio_start_seconds: null, audio_end_seconds: null, question_groups: [] };

function metadata(audio: HTMLAudioElement, duration = 1000) {
  Object.defineProperty(audio, "duration", { configurable: true, value: duration });
  fireEvent.loadedMetadata(audio);
}

describe("shared recording clips", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: vi.fn() });
    Object.defineProperty(HTMLMediaElement.prototype, "load", { configurable: true, value: vi.fn() });
  });
  afterEach(() => vi.useRealTimers());

  it("parses strict MM:SS and formats absolute recording positions", () => {
    expect(parseAudioTime("07:48")).toBe(468);
    expect(parseAudioTime("120:00")).toBe(7200);
    expect(formatAudioTime(931)).toBe("15:31");
    expect(formatAudioTime(468.9)).toBe("07:48");
    for (const input of ["", "7", "07:60", "-01:00", "07:4", "07:48.5", "1:02:03"]) expect(parseAudioTime(input)).toBeNull();
  });

  it("positions without autoplay and presents section-relative time with bounded seeking", () => {
    const view = render(<ListeningAudioPlayer src="/fictional.mp3" clip={{ startSeconds: 468, endSeconds: 931 }} />);
    const audio = view.container.querySelector("audio")!;
    expect(screen.getByRole("button", { name: "Play audio" })).toBeDisabled();
    metadata(audio);
    expect(audio.currentTime).toBe(468);
    expect(audio.play).not.toHaveBeenCalled();
    expect(screen.getByText("00:00")).toBeInTheDocument();
    expect(screen.getByText("07:43")).toBeInTheDocument();
    expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", "463");
    fireEvent.click(screen.getByRole("button", { name: "Seek backward 10 seconds" }));
    expect(audio.currentTime).toBe(468);
    fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "460" } });
    expect(audio.currentTime).toBe(928);
    fireEvent.click(screen.getByRole("button", { name: "Seek forward 10 seconds" }));
    expect(audio.currentTime).toBe(931);
  });

  it("pauses at the end and replays from the start on Play", async () => {
    const view = render(<ListeningAudioPlayer src="/fictional.mp3" clip={{ startSeconds: 60, endSeconds: 120 }} />);
    const audio = view.container.querySelector("audio")!;
    metadata(audio);
    audio.currentTime = 121;
    fireEvent.timeUpdate(audio);
    expect(audio.currentTime).toBe(120);
    expect(audio.pause).toHaveBeenCalled();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Play audio" })));
    expect(audio.currentTime).toBe(60);
    expect(screen.getByText("00:00")).toBeInTheDocument();
    expect(audio.play).toHaveBeenCalledOnce();
  });

  it("resets changed clip/source and stops the old recording on unmount", () => {
    const view = render(<ListeningAudioPlayer src="/fictional.mp3" clip={{ startSeconds: 60, endSeconds: 120 }} />);
    const audio = view.container.querySelector("audio")!;
    metadata(audio);
    audio.currentTime = 90;
    fireEvent.timeUpdate(audio);
    view.rerender(<ListeningAudioPlayer src="/fictional.mp3" clip={{ startSeconds: 120, endSeconds: 180 }} />);
    expect(audio.currentTime).toBe(120);
    expect(screen.getByText("00:00")).toBeInTheDocument();
    view.rerender(<ListeningAudioPlayer src="/replacement.mp3" clip={{ startSeconds: 30, endSeconds: 60 }} />);
    metadata(audio, 80);
    expect(audio.currentTime).toBe(30);
    expect(audio.play).not.toHaveBeenCalled();
    vi.mocked(audio.pause).mockClear();
    view.unmount();
    expect(audio.pause).toHaveBeenCalledOnce();
  });

  it.each([{ startSeconds: 20, endSeconds: 20 }, { startSeconds: -1, endSeconds: 60 }, { startSeconds: 60, endSeconds: 150 }])("rejects invalid/out-of-duration range %j without truncating it", (clip) => {
    const view = render(<ListeningAudioPlayer src="/fictional.mp3" clip={clip} />);
    const audio = view.container.querySelector("audio")!;
    metadata(audio, 120);
    fireEvent.canPlay(audio);
    expect(screen.getByRole("alert")).toHaveTextContent(/Correct the start\/end times/);
    expect(screen.getByRole("button", { name: "Play audio" })).toBeDisabled();
    expect(audio.play).not.toHaveBeenCalled();
  });

  it("keeps seek/speed policy locked while allowing clip replay", () => {
    const view = render(<ListeningAudioPlayer src="/fictional.mp3" clip={{ startSeconds: 60, endSeconds: 120 }} policy={{ allowSeeking: false, allowSpeed: false }} />);
    const audio = view.container.querySelector("audio")!;
    metadata(audio);
    expect(screen.getByLabelText("Audio seek")).toBeDisabled();
    expect(screen.getByLabelText("Playback speed")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "30" } });
    expect(audio.currentTime).toBe(60);
  });

  it("previews against the same recording and can restore whole-file playback", async () => {
    const ref = createRef<ListeningAudioPlayerHandle>();
    const view = render(<ListeningAudioPlayer ref={ref} src="/fictional.mp3" />);
    const audio = view.container.querySelector("audio")!;
    metadata(audio);
    audio.currentTime = 468;
    expect(ref.current!.currentPosition()).toBe(468);
    await act(async () => ref.current!.preview({ startSeconds: 468, endSeconds: 931 }));
    expect(view.container.querySelectorAll("audio")).toHaveLength(1);
    expect(audio.currentTime).toBe(468);
    expect(audio.play).toHaveBeenCalledOnce();
    audio.currentTime = 940; fireEvent.timeUpdate(audio);
    expect(audio.currentTime).toBe(931);
    fireEvent.click(screen.getByRole("button", { name: "Full recording" }));
    expect(screen.getByLabelText("Audio seek")).toHaveAttribute("max", "1000");
    fireEvent.change(screen.getByLabelText("Audio seek"), { target: { value: "999" } });
    expect(audio.currentTime).toBe(999);
  });

  function editor(duration: number | null = 1000) {
    const preview = vi.fn();
    render(<BuilderLifecycleProvider><ListeningSectionEditor part={part} duration={duration} currentPosition={() => 468.8} onPreview={preview} onPersisted={vi.fn()} /><BuilderAutosaveStatus /></BuilderLifecycleProvider>);
    return preview;
  }

  it("uses one revision-checked autosave for title and both ranges", async () => {
    vi.useFakeTimers();
    vi.mocked(updateListeningPart).mockImplementation(async (_id, body) => ({ ...part, ...body, revision: body.expected_revision + 1 }));
    editor();
    fireEvent.change(screen.getByLabelText("Section title / internal label"), { target: { value: "Edited section" } });
    fireEvent.change(screen.getByLabelText("Audio start (MM:SS)"), { target: { value: "07:48" } });
    fireEvent.change(screen.getByLabelText("Audio end (MM:SS)"), { target: { value: "15:31" } });
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(updateListeningPart).toHaveBeenCalledExactlyOnceWith(part.id, { title: "Edited section", order_index: 1, audio_start_seconds: 468, audio_end_seconds: 931, expected_revision: 4 });
    fireEvent.click(screen.getByRole("button", { name: "Clear audio range" }));
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(vi.mocked(updateListeningPart).mock.calls[1][1]).toMatchObject({ audio_start_seconds: null, audio_end_seconds: null, expected_revision: 5 });
  });

  it.each(["", "bad", "07:60", "07:48", "20:00"])("does not autosave intermediate/invalid end %s", async (end) => {
    vi.useFakeTimers(); editor();
    fireEvent.change(screen.getByLabelText("Audio start (MM:SS)"), { target: { value: "07:48" } });
    fireEvent.change(screen.getByLabelText("Audio end (MM:SS)"), { target: { value: end } });
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(updateListeningPart).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview section clip" })).toBeDisabled();
  });

  it("captures the current absolute position and previews the edited range", () => {
    const preview = editor();
    fireEvent.click(screen.getByRole("button", { name: "Set start to current position" }));
    expect(screen.getByLabelText("Audio start (MM:SS)")).toHaveValue("07:48");
    fireEvent.click(screen.getByRole("button", { name: "Set end to current position" }));
    expect(screen.getByLabelText("Audio end (MM:SS)")).toHaveValue("07:48");
    fireEvent.change(screen.getByLabelText("Audio end (MM:SS)"), { target: { value: "15:31" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview section clip" }));
    expect(preview).toHaveBeenCalledWith({ startSeconds: 468, endSeconds: 931 });
  });

  it("disables capture and preview until recording metadata is available", () => {
    editor(null);
    expect(screen.getByRole("button", { name: "Set start to current position" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Set end to current position" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Preview section clip" })).toBeDisabled();
  });

  it("stops autosave after a revision conflict and retains edited fields", async () => {
    vi.useFakeTimers();
    vi.mocked(updateListeningPart).mockRejectedValue(new ApiError("DRAFT_REVISION_CONFLICT", "Changed elsewhere", 409));
    editor();
    fireEvent.change(screen.getByLabelText("Audio start (MM:SS)"), { target: { value: "00:00" } });
    fireEvent.change(screen.getByLabelText("Audio end (MM:SS)"), { target: { value: "01:00" } });
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByText(/Reload the latest version/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Audio end (MM:SS)"), { target: { value: "02:00" } });
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(updateListeningPart).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Audio end (MM:SS)")).toHaveValue("02:00");
  });
});
