import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WritingReviewView } from "@/features/writing/writing-review";
import { saveWritingScore, type WritingReviewPayload } from "@/lib/api/exam";

vi.mock("@/lib/api/exam", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/exam")>();
  return { ...actual, saveWritingScore: vi.fn() };
});

const attemptId = "11111111-1111-4111-8111-111111111111";

function reviewPayload(): WritingReviewPayload {
  const now = new Date().toISOString();
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
        band_score: null,
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
        writing_task_id: "33333333-3333-4333-8333-333333333333",
        task_number: 1,
        prompt: "Describe fictional data.",
        image_asset_id: "44444444-4444-4444-8444-444444444444",
        image_asset: { id: "44444444-4444-4444-8444-444444444444", original_name: "chart.png", mime_type: "image/png", file_size: 12, content_url: "/assets/chart.png" },
        minimum_recommended_words: 150,
        recommended_duration_seconds: 1200,
        content: "A saved fictional response.",
        word_count: 5,
      },
      {
        writing_task_id: "55555555-5555-4555-8555-555555555555",
        task_number: 2,
        prompt: "Discuss a fictional proposition.",
        image_asset_id: null,
        image_asset: null,
        minimum_recommended_words: 250,
        recommended_duration_seconds: 2400,
        content: "Another response.",
        word_count: 2,
      },
    ],
  };
}

describe("WritingReviewView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(saveWritingScore).mockResolvedValue({
      ...reviewPayload().review.attempt,
      band_score: 7.5,
    });
  });

  it("shows frozen prompts, responses, image, and authoritative word count", () => {
    render(<WritingReviewView data={reviewPayload()} />);

    expect(screen.getByText("Describe fictional data.")).toBeInTheDocument();
    expect(screen.getByText("A saved fictional response.")).toBeInTheDocument();
    expect(screen.getAllByText("5 words")).not.toHaveLength(0);
    expect(screen.getByAltText("Writing Task 1 reference")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    expect(screen.getByText("Another response.")).toBeInTheDocument();
  });

  it("offers all half bands and immediately displays the saved grade", async () => {
    render(<WritingReviewView data={reviewPayload()} />);
    const select = screen.getByLabelText("Writing band score") as HTMLSelectElement;
    expect([...select.options].map((option) => option.value).filter(Boolean)).toEqual(
      Array.from({ length: 19 }, (_, index) => (index / 2).toFixed(1)),
    );
    fireEvent.change(select, { target: { value: "7.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save band score" }));

    await waitFor(() => expect(saveWritingScore).toHaveBeenCalledWith(attemptId, 7.5));
    expect(await screen.findByText("Band 7.5")).toBeInTheDocument();
  });
});
