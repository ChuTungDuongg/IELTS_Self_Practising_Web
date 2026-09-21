import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BuilderAutosaveStatus, BuilderLifecycleProvider, useBuilderAutosave } from "@/features/test-builder/builder-lifecycle";

function Harness({ save }: { save: (value: string) => Promise<unknown> }) {
  const [value, setValue] = useState("initial");
  useBuilderAutosave({ resourceKey: "fixture", value, save, valid: value !== "invalid" });
  return <><input aria-label="Draft value" value={value} onChange={(event) => setValue(event.target.value)} /><BuilderAutosaveStatus /></>;
}

function setup(save: (value: string) => Promise<unknown>) {
  render(<BuilderLifecycleProvider><Harness save={save} /></BuilderLifecycleProvider>);
}

describe("Builder autosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces a valid edit for one second and saves the latest value", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    setup(save);
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "latest" } });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(999); });
    expect(save).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(save).toHaveBeenCalledWith("latest");
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("keeps invalid data local and resumes once it is valid", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    setup(save);
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "invalid" } });
    expect(screen.getByText("Unsaved — fix validation issues")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(save).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "repaired" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(save).toHaveBeenCalledWith("repaired");
  });

  it("does not let an older response mark a newer edit as saved", async () => {
    let resolveFirst!: () => void;
    const first = new Promise<void>((resolve) => { resolveFirst = resolve; });
    const save = vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce(undefined);
    setup(save);
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "first" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText("Saving…")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "second" } });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await act(async () => { resolveFirst(); await first; });
    expect(save).toHaveBeenLastCalledWith("second");
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("preserves a failed edit and retries it on demand", async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(undefined);
    setup(save);
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "keep me" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText("Save failed")).toBeInTheDocument();
    expect(screen.getByLabelText("Draft value")).toHaveValue("keep me");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await act(async () => { await Promise.resolve(); });
    expect(save).toHaveBeenLastCalledWith("keep me");
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });
});
