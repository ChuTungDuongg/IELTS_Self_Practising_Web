import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WritingReviewView } from "@/features/writing/writing-review";
import { saveWritingTaskScore, type WritingReviewPayload } from "@/lib/api/exam";
import { listAIWritingRuns } from "@/lib/api/writing-ai";
import { assetContentUrl } from "@/lib/api/assets";

vi.mock("@/lib/api/writing-ai", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/writing-ai")>(), listAIWritingRuns: vi.fn(),
}));

vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, saveWritingTaskScore: vi.fn() };
});

const attemptId = "11111111-1111-4111-8111-111111111111";
const taskOneId = "33333333-3333-4333-8333-333333333333";
const taskTwoId = "55555555-5555-4555-8555-555555555555";
const taskOneScore = { ta: 7, cc: 6.5, lr: 7, gra: 6.5, overall: 6.75 };
const taskTwoScore = { ta: 7, cc: 7, lr: 7, gra: 7, overall: 7 };

function reviewPayload({ taskOne = null, taskTwo = null }: {
  taskOne?: typeof taskOneScore | null;
  taskTwo?: typeof taskTwoScore | null;
} = {}): WritingReviewPayload {
  const now = new Date().toISOString();
  const completed = taskOne !== null && taskTwo !== null;
  return {
    review: {
      attempt: {
        attempt_id: attemptId,
        test_version_id: "22222222-2222-4222-8222-222222222222",
        module: "WRITING",
        status: "SUBMITTED",
        finished_reason: "USER_SUBMIT",
        timer_mode: "COUNT_UP",
        timer_limit_seconds: null,
        started_at: now,
        paused_at: null,
        total_paused_seconds: 0,
        deadline_at: null,
        last_active_at: now,
        finished_at: now,
        elapsed_seconds: 120,
        remaining_seconds: null,
        raw_score: null,
        max_score: null,
        band_score: completed ? 7 : null,
        server_time: now,
      },
      test_title: "Fictional Writing review",
      answers: [],
      writing_responses: [],
      highlights: [],
      flags: [],
    },
    tasks: [
      {
        writing_task_id: taskOneId,
        task_number: 1,
        prompt: "Describe fictional data.",
        image_asset_id: "44444444-4444-4444-8444-444444444444",
        image_asset: { id: "44444444-4444-4444-8444-444444444444", original_name: "chart.png", mime_type: "image/png", file_size: 12, content_url: "/assets/chart.png" },
        minimum_recommended_words: 150,
        recommended_duration_seconds: 1200,
        content: "A saved fictional response.",
        word_count: 5,
        score: taskOne,
      },
      {
        writing_task_id: taskTwoId,
        task_number: 2,
        prompt: "Discuss a fictional proposition.",
        image_asset_id: null,
        image_asset: null,
        minimum_recommended_words: 250,
        recommended_duration_seconds: 2400,
        content: "Another response.",
        word_count: 2,
        score: taskTwo,
      },
    ],
    task1_overall: taskOne?.overall ?? null,
    task2_overall: taskTwo?.overall ?? null,
    weighted_overall: completed ? 6.9166666667 : null,
    band_score: completed ? 7 : null,
  };
}

function selectTaskScores(taskNumber: number, values: [string, string, string, string]) {
  for (const [index, criterion] of ["TA", "CC", "LR", "GRA"].entries()) {
    fireEvent.change(screen.getByLabelText(`Task ${taskNumber} ${criterion}`), {
      target: { value: values[index] },
    });
  }
}

describe("WritingReviewView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: false, items: [] });
  });

  it("shows review content and two four-criterion assessment cards", () => {
    render(<WritingReviewView data={reviewPayload()} />);

    expect(screen.getByText("Describe fictional data.")).toBeInTheDocument();
    expect(screen.getByText("A saved fictional response.")).toBeInTheDocument();
    expect(screen.getByAltText("Writing Task 1 reference")).toBeInTheDocument();
    expect(screen.getAllByText("TA")).toHaveLength(2);
    expect(screen.getAllByText("CC")).toHaveLength(2);
    expect(screen.getAllByText("LR")).toHaveLength(2);
    expect(screen.getAllByText("GRA")).toHaveLength(2);
    expect(screen.queryByLabelText("Writing band score")).not.toBeInTheDocument();
    expect(screen.getByText("Waiting for all 8 criterion scores")).toBeInTheDocument();
    expect(screen.getByText("Saved response")).toHaveClass("writing-response-kicker");
    const taskOneTa = screen.getByLabelText("Task 1 TA") as HTMLSelectElement;
    expect([...taskOneTa.options].map((option) => option.value).filter(Boolean)).toEqual(
      Array.from({ length: 19 }, (_, index) => (index / 2).toFixed(1)),
    );
    expect(screen.getByRole("button", { name: "Save Task 1 scores" })).toBeDisabled();
  });

  it.each([1, 2])("reviews and assesses only focused Task %i without weighted Writing scores", async (taskNumber) => {
    const data = reviewPayload();
    const task = data.tasks[taskNumber - 1];
    data.tasks = [task];
    data.review.attempt.scope = "FOCUSED_UNIT";
    data.review.attempt.focused_unit = { kind: "WRITING_TASK", id: task.writing_task_id, order_index: taskNumber - 1, label: `Task ${taskNumber}`, title: null };
    const { rerender } = render(<WritingReviewView data={data} />);
    expect(screen.getByText("Writing · Focused practice")).toBeInTheDocument();
    expect(screen.getAllByText("Not graded")).toHaveLength(2);
    expect(screen.queryByText(/Weighted overall|Task weighting|Waiting for all 8/)).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`Task ${taskNumber === 1 ? 2 : 1} assessment`)).not.toBeInTheDocument();
    await waitFor(() => expect(listAIWritingRuns).toHaveBeenCalledWith(attemptId, task.writing_task_id));
    expect(vi.mocked(listAIWritingRuns).mock.calls.every(([, taskId]) => taskId === task.writing_task_id)).toBe(true);
    const graded = { ...data, tasks: [{ ...task, score: taskOneScore }] };
    rerender(<WritingReviewView key="graded" data={graded} />);
    expect(screen.getByText("Task score 6.75")).toBeInTheDocument();
    expect(screen.queryByText(/Band|Weighted overall|Task weighting/)).not.toBeInTheDocument();
    await waitFor(() => expect(listAIWritingRuns).toHaveBeenCalledWith(attemptId, task.writing_task_id));
  });

  it("preserves authored paragraphs, CRLF, whitespace and word count without changing essay content", () => {
    const data = reviewPayload();
    const content = "  First fictional paragraph.\r\n\r\nSecond fictional paragraph.\r\n  \r\nThird paragraph with https://example.test/a-long-path.\r\nFourth paragraph.";
    data.tasks[0].content = content;
    data.tasks[0].word_count = 293;
    render(<WritingReviewView data={data} />);
    const reader = screen.getByRole("article", { name: "Saved Task 1 response" });
    expect(within(reader).getByRole("heading", { name: "Task 1 response" })).toBeInTheDocument();
    expect(within(reader).getByText("293 words")).toBeInTheDocument();
    expect([...reader.querySelectorAll(".writing-review-response-body > p")].map((paragraph) => paragraph.textContent)).toEqual([
      "  First fictional paragraph.", "Second fictional paragraph.",
      "Third paragraph with https://example.test/a-long-path.", "Fourth paragraph.",
    ]);
    expect(data.tasks[0].content).toBe(content);
    expect(within(reader).queryByRole("textbox")).not.toBeInTheDocument();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
  });

  it("keeps a response without line breaks as one paragraph without inventing breaks", () => {
    const data = reviewPayload();
    data.tasks[0].content = "One sentence. Another sentence! A final sentence?";
    render(<WritingReviewView data={data} />);
    const paragraphs = screen.getByRole("article", { name: "Saved Task 1 response" }).querySelectorAll(".writing-review-response-body > p");
    expect(paragraphs).toHaveLength(1);
    expect(paragraphs[0].textContent).toBe(data.tasks[0].content);
  });

  it.each(["", " \r\n\r\n  "])("shows the empty response fallback for %j", (content) => {
    const data = reviewPayload(); data.tasks[0].content = content; data.tasks[0].word_count = 0;
    render(<WritingReviewView data={data} />);
    const reader = screen.getByRole("article", { name: "Saved Task 1 response" });
    expect(within(reader).getByText("No response was saved.")).toBeInTheDocument();
    expect(within(reader).getByText("0 words")).toBeInTheDocument();
  });

  it("switches the reader, count, prompt and shared AI panel and restores Task 1 image", async () => {
    const data = reviewPayload();
    data.tasks[1].content = "Task two introduction.\n\nTask two conclusion.";
    data.tasks[1].word_count = 7;
    render(<WritingReviewView data={data} />);
    expect(screen.getByAltText("Writing Task 1 reference")).toHaveAttribute("src", assetContentUrl(data.tasks[0].image_asset!));
    expect(listAIWritingRuns).toHaveBeenCalledWith(attemptId, taskOneId);
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    const reader = screen.getByRole("article", { name: "Saved Task 2 response" });
    expect(within(reader).getByRole("heading", { name: "Task 2 response" })).toBeInTheDocument();
    expect(within(reader).getByText("7 words")).toBeInTheDocument();
    expect([...reader.querySelectorAll(".writing-review-response-body > p")].map((paragraph) => paragraph.textContent)).toEqual(["Task two introduction.", "Task two conclusion."]);
    expect(screen.getByText("Discuss a fictional proposition.")).toBeInTheDocument();
    expect(screen.queryByText("A saved fictional response.")).not.toBeInTheDocument();
    expect(screen.queryByAltText("Writing Task 1 reference")).not.toBeInTheDocument();
    await screen.findByText("Chấm AI chưa được cấu hình.");
    fireEvent.click(screen.getByRole("tab", { name: /Task 1/ }));
    expect(within(screen.getByRole("article", { name: "Saved Task 1 response" })).getByText("A saved fictional response.")).toBeInTheDocument();
    expect(screen.getByAltText("Writing Task 1 reference")).toBeInTheDocument();
    expect(screen.getByText("Describe fictional data.")).toBeInTheDocument();
    expect(screen.getByText("Minimum 150 words")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Đánh giá AI · Task 1" })).toBeInTheDocument();
    expect(listAIWritingRuns).toHaveBeenCalledTimes(3);
  });

  it("saves all Task 1 criteria and keeps the final band pending", async () => {
    vi.mocked(saveWritingTaskScore).mockResolvedValue(reviewPayload({ taskOne: taskOneScore }));
    render(<WritingReviewView data={reviewPayload()} />);
    selectTaskScores(1, ["7.0", "6.5", "7.0", "6.5"]);
    fireEvent.click(screen.getByRole("button", { name: "Save Task 1 scores" }));

    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenCalledWith(attemptId, taskOneId, {
      ta: 7, cc: 6.5, lr: 7, gra: 6.5,
      ta_feedback: null, cc_feedback: null, lr_feedback: null, gra_feedback: null,
    }));
    expect(await screen.findByText("Overall 6.75")).toBeInTheDocument();
    expect(screen.getByText("Waiting for all 8 criterion scores")).toBeInTheDocument();
  });

  it("saves Task 2, renders the final band, and refreshes it after an edit", async () => {
    const completed = reviewPayload({ taskOne: taskOneScore, taskTwo: taskTwoScore });
    vi.mocked(saveWritingTaskScore).mockResolvedValueOnce(completed).mockResolvedValueOnce({
      ...completed,
      task1_overall: 9,
      weighted_overall: 7.6666666667,
      band_score: 7.5,
      review: {
        ...completed.review,
        attempt: { ...completed.review.attempt, band_score: 7.5 },
      },
      tasks: completed.tasks.map((task) => task.task_number === 1 ? {
        ...task,
        score: { ta: 9, cc: 9, lr: 9, gra: 9, overall: 9 },
      } : task),
    });
    render(<WritingReviewView data={reviewPayload({ taskOne: taskOneScore })} />);
    selectTaskScores(2, ["7.0", "7.0", "7.0", "7.0"]);
    fireEvent.click(screen.getByRole("button", { name: "Save Task 2 scores" }));
    expect(await screen.findAllByText("Band 7.0")).toHaveLength(2);
    expect(screen.getByText("6.92")).toBeInTheDocument();
    expect(saveWritingTaskScore).toHaveBeenCalledWith(attemptId, taskTwoId, {
      ta: 7, cc: 7, lr: 7, gra: 7,
      ta_feedback: null, cc_feedback: null, lr_feedback: null, gra_feedback: null,
    });

    selectTaskScores(1, ["9.0", "9.0", "9.0", "9.0"]);
    fireEvent.click(screen.getByRole("button", { name: "Save Task 1 scores" }));
    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenLastCalledWith(attemptId, taskOneId, {
      ta: 9, cc: 9, lr: 9, gra: 9,
      ta_feedback: null, cc_feedback: null, lr_feedback: null, gra_feedback: null,
    }));
    expect(await screen.findByText("Overall 9.00")).toBeInTheDocument();
    expect(screen.getAllByText("Band 7.5")).toHaveLength(2);
  });

  it("saves optional criterion feedback and sends cleared whitespace as null", async () => {
    vi.mocked(saveWritingTaskScore).mockResolvedValue(reviewPayload({ taskOne: taskOneScore }));
    render(<WritingReviewView data={reviewPayload()} />);
    selectTaskScores(1, ["7.0", "6.5", "7.0", "6.5"]);
    fireEvent.change(screen.getByLabelText("Task 1 TA feedback"), { target: { value: "  Strong coverage.  " } });
    fireEvent.change(screen.getByLabelText("Task 1 CC feedback"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save Task 1 scores" }));
    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenCalledWith(attemptId, taskOneId, {
      ta: 7, cc: 6.5, lr: 7, gra: 6.5,
      ta_feedback: "Strong coverage.", cc_feedback: null, lr_feedback: null, gra_feedback: null,
    }));
  });

  it("reloads previously saved criterion feedback", () => {
    const scoredWithFeedback = { ...taskOneScore, ta_feedback: "Previously saved feedback." };
    render(<WritingReviewView data={reviewPayload({ taskOne: scoredWithFeedback })} />);
    expect(screen.getByLabelText("Task 1 TA feedback")).toHaveValue("Previously saved feedback.");
  });
});
