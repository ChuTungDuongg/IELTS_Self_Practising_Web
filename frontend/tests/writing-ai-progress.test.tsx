import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import styles from "@/features/writing/writing-ai-assessment.module.css";
import { ScoringProgress, activityFromEvent } from "@/features/writing/writing-ai-progress";
import { aiEventSchema, type AIWritingRun } from "@/lib/api/writing-ai";

afterEach(() => { cleanup(); vi.useRealTimers(); });

it.each(["collecting_evidence", "retrying"] as const)("animates only the active marker in phase %s", (phase) => {
  render(<ScoringProgress run={{ ...active, activity: { ...active.activity!, phase } }} />);
  const current = screen.getByLabelText("Tiến trình Task Response");
  expect(current).toHaveAttribute("data-state", phase === "retrying" ? "RETRYING" : "ACTIVE");
  expect(within(current).getByText("●")).toHaveClass(styles.activeMarker);
  const waiting = screen.getByLabelText("Tiến trình Lexical Resource");
  expect(waiting).toHaveAttribute("data-state", "WAITING");
  expect(within(waiting).getByText("○")).not.toHaveClass(styles.activeMarker);
});

it("keeps completed and genuine failure markers static", () => {
  render(<ScoringProgress run={{ ...active, status: "FAILED", progress: { ta: criterion }, failures: { cc: { error_code: "AI_PROVIDER_BAD_RESPONSE", error_message: "Failed" } }, activity: null }} />);
  expect(within(screen.getByLabelText("Tiến trình Task Response")).getByText("✓")).not.toHaveClass(styles.activeMarker);
  expect(within(screen.getByLabelText("Tiến trình Coherence & Cohesion")).getByText("×")).not.toHaveClass(styles.activeMarker);
});

it("stops unfinished criteria neutrally and preserves completed criteria after user cancellation", () => {
  render(<ScoringProgress run={{ ...active, status: "FAILED", error_code: "AI_GRADING_CANCELLED", progress: { ta: criterion, cc: criterion }, activity: { ...active.activity!, criterion: "lr", stage: "scoring" } }} />);
  expect(screen.getByText("2 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
  expect(screen.getByText("Đã dừng chấm AI.")).toBeInTheDocument();
  expect(screen.getAllByText("Đã chấm xong")).toHaveLength(2);
  expect(screen.getAllByText("Chưa hoàn tất do bạn đã dừng chấm")).toHaveLength(2);
  expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "STOPPED");
  expect(screen.queryByText("×")).not.toBeInTheDocument();
  expect(screen.queryByText("Chưa thể hoàn tất toàn bộ bài chấm.")).not.toBeInTheDocument();
});

it("keeps the rotating ring outside the 28px layout and static for reduced motion", () => {
  const css = readFileSync(resolve(process.cwd(), "src/features/writing/writing-ai-assessment.module.css"), "utf8");
  expect(css).toMatch(/\.marker\s*\{[^}]*width: 28px; height: 28px/);
  expect(css).toMatch(/\.activeMarker::after\s*\{[^}]*position: absolute;[^}]*inset: -4px;[^}]*border-top-color: var\(--writing\);[^}]*activityRotate 1\.2s linear infinite/);
  expect(css).toMatch(/prefers-reduced-motion: reduce[^}]*\.activeMarker, \.activeMarker::after\s*\{ animation: none;/);
  expect(css).toContain(".actions > button { width: 100%; }");
  expect(css).not.toContain("activityPulse");
});

it.each([
  ["chart_specialist.started", "Đang đối chiếu dữ liệu biểu đồ…"],
  ["chart_specialist.completed", "Đã đọc dữ liệu bằng bộ đọc biểu đồ chuyên dụng"],
  ["chart_reconciliation.completed", "Đã đối chiếu dữ liệu biểu đồ"],
  ["chart_specialist.failed", "Không thể dùng bộ đối chiếu chuyên dụng; tiếp tục với phân tích hình chính."],
] as const)("restores semantic chart progress from SSE: %s", (eventType, label) => {
  const event = aiEventSchema.parse({ sequence: 1, event_type: eventType, created_at: active.created_at, payload: { criterion: "ta", stage: "chart_cross_check" } });
  render(<ScoringProgress taskNumber={1} run={{ ...active, task_number: 1, activity: activityFromEvent(event) }} />);
  expect(screen.getAllByText(label)).toHaveLength(2);
  expect(screen.getByLabelText("Tiến trình Task Achievement")).toHaveAttribute("data-state", "ACTIVE");
  expect(screen.queryByText("Không thể hoàn tất tiêu chí này.")).not.toBeInTheDocument();
});

const criterion = { score: 7.5, feedback: "Lập trường nhất quán.", strengths: [], improvements: [], evidence: [] };
const active: AIWritingRun = {
  id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", writing_task_id: "33333333-3333-4333-8333-333333333333",
  status: "RUNNING", provider: "fake", model: "fake", prompt_version: "mts-task2-v2",
  result: null, progress: {}, error_code: null, error_message: null,
  created_at: "2026-10-08T00:00:00Z", started_at: null, completed_at: null,
  activity: { phase: "collecting_evidence", criterion: "ta", stage: "evidence", started_at: "2026-10-08T00:00:00Z" },
};

it("keeps Task Achievement active during fact-stage fallback and restores its SSE state", () => {
  const event = aiEventSchema.parse({ sequence: 1, event_type: "derived_facts.failed", created_at: active.created_at, payload: { criterion: "ta", stage: "derived_facts", error_code: "AI_DERIVED_FACTS_FAILED" } });
  render(<ScoringProgress taskNumber={1} run={{ ...active, task_number: 1, activity: activityFromEvent(event) }} />);
  expect(screen.getAllByText("Chưa tổng hợp đủ dữ kiện; tiếp tục với phân tích hình chính.")).toHaveLength(2);
  expect(screen.getByLabelText("Tiến trình Task Achievement")).toHaveAttribute("data-state", "ACTIVE");
  expect(screen.queryByText("Không thể hoàn tất tiêu chí này.")).not.toBeInTheDocument();
});

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

it("restores incomplete Task 1 verification without claiming completion or failing TA", () => {
  render(<ScoringProgress taskNumber={1} run={{ ...active, task_number: 1, activity: { ...active.activity!, phase: "claim_verification_failed", stage: "claim_verification" } }} />);
  expect(screen.getAllByText("Một phần đối chiếu chưa hoàn tất; tiếp tục từ thông tin hình đã đọc được.")).toHaveLength(2);
  expect(screen.getByLabelText("Tiến trình Task Achievement")).toHaveAttribute("data-state", "ACTIVE");
  expect(screen.queryByText("Đã đối chiếu các nhận định với hình")).not.toBeInTheDocument();
  expect(screen.queryByText("Không thể hoàn tất tiêu chí này.")).not.toBeInTheDocument();
});
