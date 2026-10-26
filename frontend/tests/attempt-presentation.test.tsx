import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StartAttempt } from "@/features/exam/start-attempt";
import { StartFocusedPractice } from "@/features/practice/start-focused-practice";
import { presentationStorageKey, rememberAttemptPresentation, resolveAttemptPresentation, useAttemptPresentation } from "@/features/exam/attempt-presentation";
import type { AttemptResponse } from "@/lib/api/attempts";
import { startAttempt } from "@/lib/api/attempts";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/attempts", () => ({ startAttempt: vi.fn() }));
const attempt = { attempt_id: "fictional-attempt", module: "READING" as const, attempt_context: "STANDALONE" as const, test_session_id: null };

beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });

describe("per-attempt presentation boundary", () => {
  it.each(["PRACTICE", "EXAM", "invalid", null])("always keeps Full Mock in Exam even with preference %s", preference => {
    expect(resolveAttemptPresentation({ ...attempt, attempt_context: "FULL_MOCK" }, preference)).toBe("EXAM");
    expect(resolveAttemptPresentation({ ...attempt, test_session_id: "mock" }, preference)).toBe("EXAM");
  });
  it("falls back for old attempts and never changes Writing or Speaking", () => {
    expect(resolveAttemptPresentation(attempt, null)).toBe("EXAM");
    expect(resolveAttemptPresentation(attempt, "corrupted")).toBe("EXAM");
    for (const module of ["WRITING", "SPEAKING"] as const) expect(resolveAttemptPresentation({ ...attempt, module }, "PRACTICE")).toBe("EXAM");
  });
  it("survives remount/resume for the same ID and isolates other attempts", () => {
    function Probe({ id = attempt.attempt_id }) { return <p>{useAttemptPresentation({ ...attempt, attempt_id: id })}</p>; }
    rememberAttemptPresentation(attempt, "PRACTICE");
    const view = render(<Probe />);
    expect(screen.getByText("PRACTICE")).toBeInTheDocument();
    view.unmount();
    const resumed = render(<Probe />);
    expect(screen.getByText("PRACTICE")).toBeInTheDocument();
    resumed.rerender(<Probe id="another-attempt" />);
    expect(screen.getByText("EXAM")).toBeInTheDocument();
    act(() => rememberAttemptPresentation({ ...attempt, attempt_id: "another-attempt" }, "PRACTICE"));
    expect(screen.getByText("PRACTICE")).toBeInTheDocument();
  });
  it("keeps attempts accessible when storage is denied", () => {
    const getter = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    function Probe() { return <p>{useAttemptPresentation(attempt)}</p>; }
    render(<Probe />);
    expect(screen.getByText("EXAM")).toBeInTheDocument();
    getter.mockRestore();
  });
});

describe("standalone launch preference", () => {
  it.each(["READING", "LISTENING"] as const)("defaults a new %s start to Practice without adding API fields", async module => {
    vi.mocked(startAttempt).mockResolvedValue({ ...attempt, module } as AttemptResponse);
    render(<StartAttempt versionId="fictional-version" module={module} />);
    expect(screen.getByRole("radio", { name: "Practice" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: `Start ${module === "READING" ? "Reading" : "Listening"}` }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/attempt/${attempt.attempt_id}`));
    expect(localStorage.getItem(presentationStorageKey(attempt.attempt_id))).toBe("PRACTICE");
    expect(startAttempt).toHaveBeenCalledWith({ test_version_id: "fictional-version", module, timer: { mode: "COUNTDOWN", duration_seconds: 3600 } });
  });
  it("remembers the chosen Exam presentation for a focused unit and preserves scope", async () => {
    vi.mocked(startAttempt).mockResolvedValue(attempt as AttemptResponse);
    render(<StartFocusedPractice versionId="version" target={{ module: "READING", unitId: "unit" }} />);
    fireEvent.click(screen.getByRole("radio", { name: "Exam" }));
    fireEvent.click(screen.getByRole("button", { name: "Start focused practice" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(localStorage.getItem(presentationStorageKey(attempt.attempt_id))).toBe("EXAM");
    expect(startAttempt).toHaveBeenCalledWith({ test_version_id: "version", module: "READING", scope: "FOCUSED_UNIT", focused_unit: { kind: "READING_PASSAGE", id: "unit" }, timer: { mode: "COUNTDOWN", duration_seconds: 1200 } });
  });
  it("does not expose a Reading/Listening presentation option for Writing", () => {
    render(<StartAttempt versionId="version" module="WRITING" />);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
});
