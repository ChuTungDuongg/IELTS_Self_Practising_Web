import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { StartFullMock } from "@/features/exam/start-full-mock";
import { TestSessionTransition } from "@/features/exam/test-session-transition";
import { sessionPresentationStorageKey, useAttemptPresentation } from "@/features/exam/attempt-presentation";
import type { AttemptResponse } from "@/lib/api/attempts";
import { advanceTestSession, startTestSession, type TestSession } from "@/lib/api/test-sessions";

const { push, refresh } = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/lib/api/test-sessions", () => ({ startTestSession: vi.fn(), advanceTestSession: vi.fn() }));

const startedAt = "2026-10-26T00:00:00Z";
const listening: AttemptResponse = {
  attempt_id: "11111111-1111-4111-8111-111111111111", test_version_id: "22222222-2222-4222-8222-222222222222",
  test_session_id: "33333333-3333-4333-8333-333333333333", attempt_context: "FULL_MOCK", module: "LISTENING",
  status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNTDOWN", timer_limit_seconds: 3600,
  started_at: startedAt, paused_at: null, total_paused_seconds: 0, deadline_at: "2026-10-26T01:00:00Z",
  last_active_at: startedAt, finished_at: null, elapsed_seconds: 0, remaining_seconds: 3600,
  raw_score: null, max_score: null, band_score: null, server_time: startedAt,
};
const session: TestSession = {
  session_id: listening.test_session_id!, test_version_id: listening.test_version_id, test_title: "Fictional Full Mock",
  version_number: 1, status: "IN_PROGRESS", started_at: startedAt, finished_at: null,
  current_module: "LISTENING", next_module: "READING", current_attempt: listening,
  module_order: ["LISTENING", "READING", "WRITING", "SPEAKING"], attempts: [], warnings: [], overall_band_score: null,
};
function PresentationProbe({ attempt }: { attempt: AttemptResponse }) { return <p>{useAttemptPresentation(attempt)}</p>; }

beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });

it.each([
  { label: "Practice", value: "PRACTICE" },
  { label: "Legacy", value: "EXAM" },
] as const)("keeps the $label choice through a server-created next module and remount", async ({ label, value }) => {
  vi.mocked(startTestSession).mockResolvedValue({ session, current_attempt: listening });
  const launch = render(<StartFullMock versionId={session.test_version_id} />);
  fireEvent.click(screen.getByRole("button", { name: "Start Full Mock" }));
  expect(startTestSession).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("radio", { name: label }));
  fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith(`/attempt/${listening.attempt_id}`));
  expect(startTestSession).toHaveBeenCalledExactlyOnceWith(session.test_version_id);
  expect(localStorage.getItem(sessionPresentationStorageKey(session.session_id))).toBe(value);
  launch.unmount();

  const reading = { ...listening, attempt_id: "44444444-4444-4444-8444-444444444444", module: "READING" as const };
  const next = { ...session, current_attempt: reading, current_module: "READING" as const, next_module: "WRITING" as const };
  vi.mocked(advanceTestSession).mockResolvedValue(next);
  const transition = render(<TestSessionTransition initial={{ ...session, current_attempt: null, attempts: [{ attempt_id: listening.attempt_id, module: "LISTENING", status: "SUBMITTED", raw_score: null, max_score: null, band_score: null, elapsed_seconds: 3600 }] }} />);
  fireEvent.click(screen.getByRole("button", { name: "Continue to Reading" }));
  await waitFor(() => expect(push).toHaveBeenLastCalledWith(`/attempt/${reading.attempt_id}`));
  expect(advanceTestSession).toHaveBeenCalledExactlyOnceWith(session.session_id);
  transition.unmount();
  const runner = render(<PresentationProbe attempt={reading} />);
  expect(screen.getByText(value)).toBeInTheDocument();
  runner.unmount();
  render(<PresentationProbe attempt={reading} />);
  expect(screen.getByText(value)).toBeInTheDocument();
});

it("cancels Full Mock presentation selection and returns focus before any request", () => {
  render(<StartFullMock versionId={session.test_version_id} />);
  const trigger = screen.getByRole("button", { name: "Start Full Mock" });
  trigger.focus(); fireEvent.click(trigger);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(startTestSession).not.toHaveBeenCalled();
  expect(localStorage.getItem(sessionPresentationStorageKey(session.session_id))).toBeNull();
});
