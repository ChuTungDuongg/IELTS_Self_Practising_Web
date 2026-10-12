import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { LibraryVersionContent } from "@/features/practice/library-content";
import { TestSessionTransition } from "@/features/exam/test-session-transition";
import { advanceTestSession, testSessionSchema } from "@/lib/api/test-sessions";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";

const push = vi.fn(); const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("@/features/exam/start-attempt", () => ({ StartAttempt: ({ module }: { module: string }) => <button>Start {module}</button> }));
vi.mock("@/lib/api/test-sessions", async (original) => ({ ...await original<typeof import("@/lib/api/test-sessions")>(), advanceTestSession: vi.fn() }));
const id = (digit: number) => `${digit}${"1".repeat(7)}-1111-4111-8111-${"1".repeat(12)}`;
const order = ["LISTENING", "READING", "WRITING", "SPEAKING"] as const;
const modules = order.map((module_type, index) => ({ id: id(index + 1), module_type, title: null, recommended_duration_seconds: module_type === "SPEAKING" ? 900 : 3600, question_count: module_type === "READING" || module_type === "LISTENING" ? 40 : 0, passage_count: 0, listening_part_count: 0, writing_task_count: 0 }));
const version = { id: id(5), test_id: id(6), test_title: "Fictional four-skill test", version_number: 1, modules } as unknown as VersionDetail;
const test = { title: version.test_title, origin: "ADMIN", description: "Fictional authored test" } as TestSummary;
const base = { session_id: id(7), test_version_id: version.id, test_title: version.test_title, version_number: 1, status: "IN_PROGRESS", started_at: "2026-10-12T00:00:00Z", finished_at: null, current_module: "WRITING", next_module: "SPEAKING", current_attempt: null, warnings: [], overall_band_score: null, module_order: [...order], attempts: [{ attempt_id: id(3), module: "WRITING", status: "SUBMITTED", band_score: 7, raw_score: null, max_score: null, elapsed_seconds: 3600 }] };
beforeEach(() => vi.clearAllMocks());
it("requires Speaking for new Full Mock while keeping individual modules accessible", () => {
  render(<LibraryVersionContent test={test} version={{ ...version, modules: version.modules.filter((module) => module.module_type !== "SPEAKING") }} />);
  expect(screen.queryByRole("button", { name: "Start Full Mock" })).toBeNull(); expect(screen.getByText("Full Mock unavailable: Speaking module is missing.")).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Start WRITING" })).toBeInTheDocument();
});
it("requires a configured Speaking module duration for Full Mock", () => {
  render(<LibraryVersionContent test={test} version={{ ...version, modules: version.modules.map((module) => module.module_type === "SPEAKING" ? { ...module, recommended_duration_seconds: null } : module) }} />);
  expect(screen.queryByRole("button", { name: "Start Full Mock" })).toBeNull(); expect(screen.getByText("Full Mock unavailable: Speaking recommended duration is missing.")).toBeInTheDocument();
});
it("offers the application's four-skill order for a ready test", () => {
  render(<LibraryVersionContent test={test} version={version} />);
  expect(screen.getByRole("heading", { name: "Listening → Reading → Writing → Speaking" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Start Full Mock" })).toBeEnabled();
});
it("parses Writing to Speaking and continues through the existing Speaking attempt route", async () => {
  const session = testSessionSchema.parse(base); const next = { ...session, current_attempt: { attempt_id: id(4), module: "SPEAKING" } } as typeof session;
  vi.mocked(advanceTestSession).mockResolvedValue(next); render(<TestSessionTransition initial={session} />);
  expect(screen.getByRole("heading", { name: "Writing complete" })).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Continue to Speaking" }));
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith(`/attempt/${id(4)}`)); expect(refresh).not.toHaveBeenCalled();
});
it("shows all four completed module bands and leaves overall unavailable when Speaking is ungraded", () => {
  const attempts = order.map((module, index) => ({ ...base.attempts[0], attempt_id: id(index + 1), module, band_score: module === "SPEAKING" ? null : 7 }));
  render(<TestSessionTransition initial={testSessionSchema.parse({ ...base, status: "COMPLETED", current_module: null, next_module: null, attempts })} />);
  const speaking = screen.getByText("Speaking").parentElement!; expect(within(speaking).getByText("—")).toBeInTheDocument(); expect(screen.getByText("Overall").parentElement).toHaveTextContent("—"); expect(screen.queryByRole("button", { name: /Continue to/ })).toBeNull();
});
it("preserves legacy three-module completion without inventing a Speaking result", () => {
  const legacy = { ...base, module_order: undefined };
  render(<TestSessionTransition initial={testSessionSchema.parse({ ...legacy, status: "COMPLETED", current_module: null, next_module: null, overall_band_score: 7, attempts: order.slice(0, 3).map((module, index) => ({ ...base.attempts[0], attempt_id: id(index + 1), module })) })} />);
  expect(screen.queryByText("Speaking")).toBeNull(); expect(screen.getByText("Overall").parentElement).toHaveTextContent("7.0"); expect(screen.getByText("Writing")).toBeInTheDocument();
});
