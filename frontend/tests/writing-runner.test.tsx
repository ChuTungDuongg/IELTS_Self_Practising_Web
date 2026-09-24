import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingRunner } from "@/features/writing/writing-runner";
import { getAttempt, pauseAttempt, recordActivity, saveWritingResponse } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { submitAttempt, type ExamPayload } from "@/lib/api/exam";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));
vi.mock("@/lib/api/attempts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/attempts")>();
  return { ...actual, getAttempt: vi.fn(), recordActivity: vi.fn(), saveWritingResponse: vi.fn(), pauseAttempt: vi.fn() };
});
vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, submitAttempt: vi.fn(), getExam: vi.fn() };
});

const attemptId = "11111111-1111-4111-8111-111111111111";
const taskOneId = "22222222-2222-4222-8222-222222222222";
const taskTwoId = "33333333-3333-4333-8333-333333333333";

function deferred() {
  let resolve!: (value: never) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<never>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function payload(): ExamPayload {
  const now = new Date().toISOString();
  return {
    attempt: {
      attempt_id: attemptId,
      test_version_id: "44444444-4444-4444-8444-444444444444",
      module: "WRITING",
      status: "IN_PROGRESS",
      finished_reason: null,
      timer_mode: "COUNT_UP",
      timer_limit_seconds: null,
      started_at: now,
      paused_at: null,
      total_paused_seconds: 0,
      deadline_at: null,
      last_active_at: now,
      finished_at: null,
      elapsed_seconds: 0,
      remaining_seconds: null,
      raw_score: null,
      max_score: null,
      band_score: null,
      server_time: now,
    },
    test_title: "Fictional Writing practice",
    passages: [],
    highlights: [],
    listening_audio_asset: null,
    listening_parts: [],
    writing_tasks: [
      {
        id: taskOneId,
        task_number: 1,
        prompt: "Describe fictional data.",
        image_asset_id: "55555555-5555-4555-8555-555555555555",
        image_asset: { id: "55555555-5555-4555-8555-555555555555", original_name: "chart.png", mime_type: "image/png", file_size: 12, content_url: "/assets/chart.png" },
        minimum_recommended_words: 150,
        recommended_duration_seconds: 1200,
        order_index: 0,
        content: "Restored Task One",
        word_count: 3,
        response_revision: 1,
      },
      {
        id: taskTwoId,
        task_number: 2,
        prompt: "Discuss a fictional proposition.",
        image_asset_id: null,
        image_asset: null,
        minimum_recommended_words: 250,
        recommended_duration_seconds: 2400,
        order_index: 1,
        content: "Restored Task Two",
        word_count: 3,
        response_revision: 1,
      },
    ],
  };
}

describe("WritingRunner", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.mocked(saveWritingResponse).mockImplementation(async (_attempt, taskId, content, expectedRevision) => ({ writing_task_id: taskId, content, word_count: 0, saved_at: new Date().toISOString(), revision: expectedRevision + 1 }));
    vi.mocked(submitAttempt).mockResolvedValue({});
    vi.mocked(pauseAttempt).mockResolvedValue({ status: "PAUSED" } as never);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("restores both task drafts, shows Task 1 image, and switches tabs", () => {
    render(<WritingRunner initial={payload()} />);

    expect(screen.getByText("Writing Task 1")).toHaveClass("writing-task-kicker");
    expect(screen.getByAltText("Writing Task 1 reference")).toBeInTheDocument();
    expect(screen.getByLabelText("Response for Task 1")).toHaveValue("Restored Task One");
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    expect(screen.getByLabelText("Response for Task 2")).toHaveValue("Restored Task Two");
    expect(screen.getByText("Discuss a fictional proposition.")).toBeInTheDocument();
  });

  it("updates local word count and autosaves after 750 ms", async () => {
    render(<WritingRunner initial={payload()} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), {
      target: { value: "It’s a city's plan for Đà Nẵng." },
    });
    expect(screen.getAllByText("7 words")).not.toHaveLength(0);

    await act(async () => vi.advanceTimersByTime(749));
    expect(saveWritingResponse).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTime(1));
    expect(saveWritingResponse).toHaveBeenCalledWith(
      attemptId,
      taskOneId,
      "It’s a city's plan for Đà Nẵng.",
      1,
    );
  });

  it("keeps a newer revision authoritative after an older save fails", async () => {
    const old = deferred();
    vi.mocked(saveWritingResponse).mockReturnValueOnce(old.promise);
    render(<WritingRunner initial={payload()} />);
    const textarea = screen.getByLabelText("Response for Task 1");
    fireEvent.change(textarea, { target: { value: "Old draft" } });
    expect(screen.getByText("Unsaved")).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(750); });
    fireEvent.change(textarea, { target: { value: "Newest draft" } });
    old.reject(new Error("old request failed"));
    await act(async () => { await Promise.resolve(); });
    expect(saveWritingResponse).toHaveBeenLastCalledWith(attemptId, taskOneId, "Newest draft", 1);
    expect(screen.queryByText("Save failed")).not.toBeInTheDocument();
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("retains a failed current revision and retries its latest content", async () => {
    vi.mocked(saveWritingResponse).mockRejectedValueOnce(new Error("offline"));
    render(<WritingRunner initial={payload()} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), { target: { value: "Retry this draft" } });
    await act(async () => { vi.advanceTimersByTime(750); });
    expect(screen.getByText("Save failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await act(async () => { await Promise.resolve(); });
    expect(saveWritingResponse).toHaveBeenLastCalledWith(attemptId, taskOneId, "Retry this draft", 1);
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("flushes both dirty tasks before Submit and prevents a second Submit", async () => {
    const first = deferred();
    const second = deferred();
    vi.mocked(saveWritingResponse).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    render(<WritingRunner initial={payload()} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), { target: { value: "Task one latest" } });
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    fireEvent.change(screen.getByLabelText("Response for Task 2"), { target: { value: "Task two latest" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit Writing" }));
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    expect(saveWritingResponse).toHaveBeenCalledWith(attemptId, taskOneId, "Task one latest", 1);
    expect(saveWritingResponse).toHaveBeenCalledWith(attemptId, taskTwoId, "Task two latest", 1);
    expect(submitAttempt).not.toHaveBeenCalled();
    first.resolve({} as never);
    await act(async () => { await Promise.resolve(); });
    expect(submitAttempt).not.toHaveBeenCalled();
    second.resolve({} as never);
    await act(async () => { await Promise.resolve(); });
    expect(submitAttempt).toHaveBeenCalledTimes(1);
  });

  it("warns before leaving only while a Writing revision is unsaved", async () => {
    render(<WritingRunner initial={payload()} />);
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), { target: { value: "Pending draft" } });
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    await act(async () => { vi.advanceTimersByTime(750); });
    const saved = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(saved);
    expect(saved.defaultPrevented).toBe(false);
  });

  it("saves immediately and saves successfully before submitting", async () => {
    render(<WritingRunner initial={payload()} />);
    const textarea = screen.getByLabelText("Response for Task 1");
    fireEvent.change(textarea, { target: { value: "Immediate save content" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Task 1" }));
    await act(async () => undefined);
    expect(saveWritingResponse).toHaveBeenCalledTimes(1);

    fireEvent.change(textarea, { target: { value: "Final saved content" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit Writing" }));
    await act(async () => undefined);
    expect(saveWritingResponse).toHaveBeenLastCalledWith(attemptId, taskOneId, "Final saved content", 2);
    expect(submitAttempt).toHaveBeenCalledWith(attemptId);
    expect(vi.mocked(saveWritingResponse).mock.invocationCallOrder.at(-1)).toBeLessThan(
      vi.mocked(submitAttempt).mock.invocationCallOrder[0],
    );
    expect(push).toHaveBeenCalledWith(`/review/${attemptId}`);
  });

  it("blocks submission and exposes a retryable error when final save fails", async () => {
    vi.mocked(saveWritingResponse).mockRejectedValueOnce(new Error("offline"));
    render(<WritingRunner initial={payload()} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), {
      target: { value: "Unsaved content" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Writing" }));

    await act(async () => undefined);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be saved");
    expect(submitAttempt).not.toHaveBeenCalled();
    expect(within(screen.getByRole("alert")).getByRole("button", { name: "Retry save" })).toBeInTheDocument();
  });

  it("blocks Submit and Pause on a Writing conflict and offers Reload latest", async () => {
    vi.mocked(saveWritingResponse).mockRejectedValueOnce(new ApiError("ATTEMPT_RESPONSE_CONFLICT", "Changed in another tab", 409));
    render(<WritingRunner initial={payload()} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), { target: { value: "Local text" } });
    await act(async () => { vi.advanceTimersByTime(750); });
    expect(screen.getByRole("button", { name: "Reload latest" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry save" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Submit Writing" }));
    await act(async () => { await Promise.resolve(); });
    expect(submitAttempt).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));
    await act(async () => { await Promise.resolve(); });
    expect(pauseAttempt).not.toHaveBeenCalled();
    expect(saveWritingResponse).toHaveBeenCalledTimes(1);
  });

  it("saves the current response before pausing and exits to history", async () => {
    render(<WritingRunner initial={payload()} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), { target: { value: "Pause-safe draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Pause & exit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause & exit" }));
    await act(async () => undefined);

    expect(saveWritingResponse).toHaveBeenCalledWith(attemptId, taskOneId, "Pause-safe draft", 1);
    expect(vi.mocked(saveWritingResponse).mock.invocationCallOrder.at(-1)).toBeLessThan(
      vi.mocked(pauseAttempt).mock.invocationCallOrder[0],
    );
    expect(push).toHaveBeenCalledWith("/history");
  });

  it("reconciles finalized Writing autosave and stops retries and heartbeat", async () => {
    const initial = payload();
    vi.mocked(saveWritingResponse).mockRejectedValueOnce(new ApiError("ATTEMPT_FINALIZED", "finalized", 409));
    vi.mocked(getAttempt).mockResolvedValue({ ...initial.attempt, status: "INTERRUPTED" });
    render(<WritingRunner initial={initial} />);
    fireEvent.change(screen.getByLabelText("Response for Task 1"), { target: { value: "Client-only text" } });
    await act(async () => vi.advanceTimersByTime(750));
    expect(push).toHaveBeenCalledWith(`/review/${attemptId}`);
    expect(screen.getByRole("status")).toHaveTextContent("Attempt finished");
    expect(screen.queryByText("Your response could not be saved")).not.toBeInTheDocument();
    fireEvent.click(window);
    await act(async () => vi.advanceTimersByTime(30_000));
    expect(saveWritingResponse).toHaveBeenCalledTimes(1);
    expect(recordActivity).not.toHaveBeenCalled();
  });
});
