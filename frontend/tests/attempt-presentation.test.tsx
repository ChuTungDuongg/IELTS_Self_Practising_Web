import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StartAttempt } from "@/features/exam/start-attempt";
import { StartFocusedPractice } from "@/features/practice/start-focused-practice";
import { presentationStorageKey, sessionPresentationStorageKey, rememberAttemptPresentation, rememberSessionPresentation, resolveAttemptPresentation, useAttemptPresentation } from "@/features/exam/attempt-presentation";
import type { AttemptResponse } from "@/lib/api/attempts";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/attempts", () => ({ startAttempt: vi.fn() }));
const attempt = { attempt_id: "fictional-attempt", module: "READING" as const, attempt_context: "STANDALONE" as const, test_session_id: null };

beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });

describe("per-attempt presentation boundary", () => {
  it.each(["PRACTICE", "EXAM"] as const)("honors explicit Full Mock preference %s", preference => {
    expect(resolveAttemptPresentation({ ...attempt, attempt_context: "FULL_MOCK" }, preference)).toBe(preference);
    expect(resolveAttemptPresentation({ ...attempt, test_session_id: "mock" }, preference)).toBe(preference);
  });
  it("falls back for old attempts and never changes Writing or Speaking", () => {
    expect(resolveAttemptPresentation(attempt, null)).toBe("EXAM");
    expect(resolveAttemptPresentation(attempt, "corrupted")).toBe("EXAM");
    for (const skill of ["WRITING", "SPEAKING"] as const) {
      expect(resolveAttemptPresentation({ ...attempt, module: skill }, "PRACTICE")).toBe("EXAM");
      expect(resolveAttemptPresentation({ ...attempt, module: skill, test_session_id: "mock" }, null, "PRACTICE")).toBe("EXAM");
    }
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
  it("resumes later Full Mock modules with their session choice and isolates other sessions", () => {
    const first = { ...attempt, attempt_context: "FULL_MOCK" as const, test_session_id: "first-session" };
    function Probe({ sessionId, id = "later-reading" }: { sessionId: string; id?: string }) { return <p>{useAttemptPresentation({ ...first, attempt_id: id, test_session_id: sessionId })}</p>; }
    rememberSessionPresentation("first-session", "PRACTICE");
    rememberSessionPresentation("second-session", "EXAM");
    const view = render(<Probe sessionId="first-session" />);
    expect(screen.getByText("PRACTICE")).toBeInTheDocument();
    view.unmount();
    const resumed = render(<Probe sessionId="first-session" />);
    expect(screen.getByText("PRACTICE")).toBeInTheDocument();
    resumed.rerender(<Probe sessionId="second-session" />);
    expect(screen.getByText("EXAM")).toBeInTheDocument();
    resumed.rerender(<Probe sessionId="old-session" />);
    expect(screen.getByText("EXAM")).toBeInTheDocument();
    act(() => rememberAttemptPresentation({ ...first, attempt_id: "later-reading" }, "EXAM"));
    resumed.rerender(<Probe sessionId="first-session" />);
    expect(screen.getByText("EXAM")).toBeInTheDocument();
    act(() => { localStorage.setItem(presentationStorageKey("later-reading"), "invalid"); window.dispatchEvent(new Event("storage")); });
    expect(screen.getByText("PRACTICE")).toBeInTheDocument();
    act(() => { localStorage.setItem(sessionPresentationStorageKey("first-session"), "invalid"); window.dispatchEvent(new Event("storage")); });
    expect(screen.getByText("EXAM")).toBeInTheDocument();
  });
});

describe("standalone launch preference", () => {
  it.each(["READING", "LISTENING"] as const)("defaults a new %s start to Practice without adding API fields", async module => {
    vi.mocked(startAttempt).mockResolvedValue({ ...attempt, module } as AttemptResponse);
    render(<StartAttempt versionId="fictional-version" module={module} />);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `Start ${module === "READING" ? "Reading" : "Listening"}` }));
    expect(screen.getByRole("dialog", { name: "Choose your interface" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Practice" })).toBeChecked();
    expect(startAttempt).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/attempt/${attempt.attempt_id}`));
    expect(localStorage.getItem(presentationStorageKey(attempt.attempt_id))).toBe("PRACTICE");
    expect(startAttempt).toHaveBeenCalledWith({ test_version_id: "fictional-version", module, timer: { mode: "COUNTDOWN", duration_seconds: 3600 } });
  });
  it("labels the original presentation Legacy and preserves the stored mode and focused scope", async () => {
    vi.mocked(startAttempt).mockResolvedValue(attempt as AttemptResponse);
    render(<StartFocusedPractice versionId="version" target={{ module: "READING", unitId: "unit" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Start focused practice" }));
    expect(screen.queryByRole("radio", { name: "Exam" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Legacy" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(localStorage.getItem(presentationStorageKey(attempt.attempt_id))).toBe("EXAM");
    expect(startAttempt).toHaveBeenCalledWith({ test_version_id: "version", module: "READING", scope: "FOCUSED_UNIT", focused_unit: { kind: "READING_PASSAGE", id: "unit" }, timer: { mode: "COUNTDOWN", duration_seconds: 1200 } });
  });
  it("does not expose a Reading/Listening presentation option for Writing", () => {
    render(<StartAttempt versionId="version" module="WRITING" />);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
  it("renders inert scaled thumbnails using published metadata and cancels without starting the timer", () => {
    const view = render(<div className="app-shell"><StartAttempt versionId="version" module="READING" preview={{ title: "Fictional <img> title", unitTitle: "Fictional trees", questionTypes: ["short_answer"], startNumber: 8, questionCount: 3 }} /></div>);
    const trigger = screen.getByRole("button", { name: "Start Reading" });
    trigger.focus(); fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(view.container.querySelector(".app-shell")).toHaveAttribute("inert");
    expect(dialog.querySelectorAll('iframe')).toHaveLength(2);
    expect(dialog.querySelectorAll('[inert][aria-hidden="true"]')).toHaveLength(2);
    expect(within(dialog).getByText(/fictional sample content/)).toBeInTheDocument();
    expect(dialog.querySelector("img, audio")).toBeNull();
    expect(screen.getByRole("radio", { name: "Practice" })).toHaveFocus();
    const confirm = screen.getByRole("button", { name: "Continue with this interface" });
    confirm.focus(); fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(view.container.querySelector(".app-shell")).not.toHaveAttribute("inert");
    expect(trigger).toHaveFocus();
    expect(startAttempt).not.toHaveBeenCalled();
    expect(localStorage.getItem(presentationStorageKey(attempt.attempt_id))).toBeNull();
  });
  it("guards repeated confirmation and cannot dismiss a pending start", async () => {
    let finish!: (value: AttemptResponse) => void;
    vi.mocked(startAttempt).mockReturnValue(new Promise(resolve => { finish = resolve; }));
    render(<StartAttempt versionId="version" module="LISTENING" />);
    fireEvent.click(screen.getByRole("button", { name: "Start Listening" }));
    const confirm = screen.getByRole("button", { name: "Continue with this interface" });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(startAttempt).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("radio", { name: "Legacy" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByRole("dialog")).toHaveFocus();
    await act(async () => finish({ ...attempt, module: "LISTENING" } as AttemptResponse));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(push).toHaveBeenCalledExactlyOnceWith(`/attempt/${attempt.attempt_id}`);
  });
  it("keeps the chosen layout and timer on a rejected start, then safely retries", async () => {
    vi.mocked(startAttempt).mockRejectedValueOnce(new ApiError("UNAVAILABLE", "Fictional temporary failure", 409)).mockResolvedValueOnce(attempt as AttemptResponse);
    render(<StartAttempt versionId="version" module="READING" />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "3000" } });
    fireEvent.click(screen.getByRole("button", { name: "Start Reading" }));
    fireEvent.click(screen.getByRole("radio", { name: "Legacy" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Fictional temporary failure"));
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: "Legacy" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(startAttempt).toHaveBeenCalledTimes(2);
    expect(vi.mocked(startAttempt).mock.calls.every(([request]) => request.timer?.duration_seconds === 3000)).toBe(true);
    expect(localStorage.getItem(presentationStorageKey(attempt.attempt_id))).toBe("EXAM");
  });
});
