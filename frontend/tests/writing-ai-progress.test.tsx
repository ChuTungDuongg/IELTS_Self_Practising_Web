import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ScoringProgress } from "@/features/writing/writing-ai-progress";
import { type AIWritingRun } from "@/lib/api/writing-ai";

afterEach(() => { cleanup(); vi.useRealTimers(); });

const criterion = { score: 7.5, feedback: "Lập trường nhất quán.", strengths: [], improvements: [], evidence: [] };
const active: AIWritingRun = {
  id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", writing_task_id: "33333333-3333-4333-8333-333333333333",
  status: "RUNNING", provider: "fake", model: "fake", prompt_version: "mts-task2-v2",
  result: null, progress: {}, error_code: null, error_message: null,
  created_at: "2026-10-08T00:00:00Z", started_at: null, completed_at: null,
  activity: { phase: "collecting_evidence", criterion: "ta", stage: "evidence", started_at: "2026-10-08T00:00:00Z" },
};

it("uses elapsed wall time only on active stages and hides ticks from announcements", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-08T00:00:12Z"));
  const view = render(<ScoringProgress run={active} />);
  expect(screen.getByText("12 giây")).toHaveAttribute("aria-hidden", "true");
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText("13 giây")).toBeInTheDocument();
  view.rerender(<ScoringProgress run={{ ...active, progress: { ta: criterion }, activity: { ...active.activity!, phase: "completed" } }} />);
  expect(screen.getByLabelText("Tiến trình Task Response")).toHaveAttribute("data-state", "COMPLETED");
  expect(screen.queryByText(/giây/)).not.toBeInTheDocument();
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
});

it("reconstructs legacy failed state from persisted partial results", () => {
  render(<ScoringProgress run={{ ...active, status: "FAILED", progress: { ta: criterion, cc: criterion }, activity: undefined, error_code: "AI_PROVIDER_BAD_RESPONSE" }} />);
  expect(screen.getByText("2 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
  expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "FAILED");
  expect(within(screen.getByLabelText("Tiến trình Grammatical Range & Accuracy")).getByText("Chưa thực hiện")).toBeInTheDocument();
  expect(screen.queryByText(/Đang (chấm|phân tích|thu thập)/)).not.toBeInTheDocument();
});

it("terminal completed state overrides an outdated transient stage", () => {
  render(<ScoringProgress run={{ ...active, status: "COMPLETED", progress: { ta: criterion, cc: criterion, lr: criterion, gra: criterion } }} />);
  expect(screen.getByText("4 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
  expect(screen.getByText("Chấm bài hoàn tất")).toBeInTheDocument();
  expect(screen.getAllByText("Đã chấm xong")).toHaveLength(4);
  expect(screen.queryByText("Đang thu thập dẫn chứng…")).not.toBeInTheDocument();
});

it("retains an interrupted terminal criterion beside an earlier persisted failure", () => {
  render(<ScoringProgress run={{ ...active, status: "FAILED", progress: { ta: criterion, cc: criterion }, failures: { lr: { error_code: "AI_PROVIDER_BAD_RESPONSE", error_message: "Không thể hoàn tất tiêu chí này.", stage: "evidence" } }, error_code: "RUN_INTERRUPTED", activity: { ...active.activity!, phase: "failed", criterion: "gra", stage: "scoring" } }} />);
  expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "FAILED");
  expect(screen.getByLabelText("Tiến trình Grammatical Range & Accuracy")).toHaveAttribute("data-state", "FAILED");
  expect(screen.getByText("2 hoàn tất · 2 lỗi")).toBeInTheDocument();
});
