import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TestSessionTransition } from "@/features/exam/test-session-transition";
import type { TestSession } from "@/lib/api/test-sessions";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

it("shows the next module without false question-count warnings for canonical 40-slot modules", () => {
  const session: TestSession = {
    session_id: "99999999-9999-4999-8999-999999999999",
    test_version_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    test_title: "Fictional Full Mock",
    version_number: 4,
    status: "IN_PROGRESS",
    started_at: "2026-09-20T00:00:00Z",
    finished_at: null,
    current_module: "WRITING",
    next_module: "WRITING",
    current_attempt: null,
    attempts: [{ attempt_id: "11111111-1111-4111-8111-111111111111", module: "READING", status: "SUBMITTED", band_score: 8, raw_score: 35, max_score: 40, elapsed_seconds: 3600 }],
    warnings: [],
    overall_band_score: null,
  };

  render(<TestSessionTransition initial={session} />);

  expect(screen.getByRole("heading", { name: "Reading complete" })).toBeInTheDocument();
  expect(screen.getByText("Writing")).toBeInTheDocument();
  expect(screen.queryByText(/has (35|39) questions/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Continue to Writing" })).toBeInTheDocument();
});
