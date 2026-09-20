import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WritingReviewView } from "@/features/writing/writing-review";
import { saveWritingTaskScore, type WritingReviewPayload } from "@/lib/api/exam";

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
  beforeEach(() => vi.clearAllMocks());

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

  it("saves all Task 1 criteria and keeps the final band pending", async () => {
    vi.mocked(saveWritingTaskScore).mockResolvedValue(reviewPayload({ taskOne: taskOneScore }));
    render(<WritingReviewView data={reviewPayload()} />);
    selectTaskScores(1, ["7.0", "6.5", "7.0", "6.5"]);
    fireEvent.click(screen.getByRole("button", { name: "Save Task 1 scores" }));

    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenCalledWith(attemptId, taskOneId, {
      ta: 7, cc: 6.5, lr: 7, gra: 6.5,
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
    });

    selectTaskScores(1, ["9.0", "9.0", "9.0", "9.0"]);
    fireEvent.click(screen.getByRole("button", { name: "Save Task 1 scores" }));
    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenLastCalledWith(attemptId, taskOneId, {
      ta: 9, cc: 9, lr: 9, gra: 9,
    }));
    expect(await screen.findByText("Overall 9.00")).toBeInTheDocument();
    expect(screen.getAllByText("Band 7.5")).toHaveLength(2);
  });
});
