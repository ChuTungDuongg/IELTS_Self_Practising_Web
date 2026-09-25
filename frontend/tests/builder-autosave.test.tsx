import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BuilderAutosaveStatus, BuilderLifecycleProvider, useBuilderAutosave } from "@/features/test-builder/builder-lifecycle";
import { ApiError } from "@/lib/api/client";

function Harness({ save }: { save: (value: string) => Promise<unknown> }) {
  const [value, setValue] = useState("initial");
  useBuilderAutosave({ resourceKey: "fixture", value, save, valid: value !== "invalid" });
  return <><input aria-label="Draft value" value={value} onChange={(event) => setValue(event.target.value)} /><BuilderAutosaveStatus /></>;
}

function DualHarness({ saveFirst, saveSecond }: {
  saveFirst: (value: string) => Promise<unknown>;
  saveSecond: (value: string) => Promise<unknown>;
}) {
  const [first, setFirst] = useState("first-initial");
  const [second, setSecond] = useState("second-initial");
  useBuilderAutosave({ resourceKey: "first", value: first, save: saveFirst });
  useBuilderAutosave({ resourceKey: "second", value: second, save: saveSecond });
  return <>
    <input aria-label="First draft" value={first} onChange={(event) => setFirst(event.target.value)} />
    <input aria-label="Second draft" value={second} onChange={(event) => setSecond(event.target.value)} />
  </>;
}

function ExplicitFlushHarness({ save }: { save: (value: string) => Promise<unknown> }) {
  const [value, setValue] = useState("initial");
  const { saveNow } = useBuilderAutosave({ resourceKey: "fixture", value, save });
  return <>
    <input aria-label="Draft value" value={value} onChange={(event) => setValue(event.target.value)} />
    <button type="button" onClick={() => { void saveNow(); void saveNow(); }}>Flush twice</button>
  </>;
}

function CanonicalHarness({ save }: { save: (value: string) => Promise<string> }) {
  const [value, setValue] = useState("initial");
  useBuilderAutosave({
    resourceKey: "canonical-fixture",
    value,
    save,
    onSaved: (saved, _submitted, unchanged) => {
      if (unchanged) {
        setValue(saved);
        return saved;
      }
    },
  });
  return <><input aria-label="Canonical draft" value={value} onChange={(event) => setValue(event.target.value)} /><BuilderAutosaveStatus /></>;
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

  it("shows the canonical server response without scheduling a duplicate save", async () => {
    const save = vi.fn(async (value: string) => value.trim());
    render(<BuilderLifecycleProvider><CanonicalHarness save={save} /></BuilderLifecycleProvider>);
    fireEvent.change(screen.getByLabelText("Canonical draft"), { target: { value: "  edited  " } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByLabelText("Canonical draft")).toHaveValue("edited");
    expect(screen.getByText("Saved")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("keeps newer typing when an older canonical response arrives", async () => {
    let resolveFirst!: (value: string) => void;
    const save = vi.fn()
      .mockImplementationOnce(() => new Promise<string>((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce("SECOND");
    render(<BuilderLifecycleProvider><CanonicalHarness save={save} /></BuilderLifecycleProvider>);
    fireEvent.change(screen.getByLabelText("Canonical draft"), { target: { value: "first" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Canonical draft"), { target: { value: "second" } });
    await act(async () => { resolveFirst("FIRST"); await Promise.resolve(); });
    expect(save).toHaveBeenLastCalledWith("second");
    expect(screen.getByLabelText("Canonical draft")).toHaveValue("SECOND");
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

  it("returns to Saved when an invalid edit is reverted to the server baseline", () => {
    const save = vi.fn().mockResolvedValue(undefined);
    setup(save);

    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "invalid" } });
    expect(screen.getByText("Unsaved — fix validation issues")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "initial" } });

    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
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

  it("persists a reversion made while an older save is in flight", async () => {
    let resolveFirst!: () => void;
    const first = new Promise<void>((resolve) => { resolveFirst = resolve; });
    const save = vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce(undefined);
    setup(save);

    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "temporary" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "initial" } });
    expect(screen.getByLabelText("Draft value")).toHaveValue("initial");

    await act(async () => { resolveFirst(); await first; });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenNthCalledWith(2, "initial");
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("lets unrelated resources save independently", async () => {
    let resolveFirst!: () => void;
    const saveFirst = vi.fn(() => new Promise<void>((resolve) => { resolveFirst = resolve; }));
    const saveSecond = vi.fn().mockResolvedValue(undefined);
    render(<BuilderLifecycleProvider><DualHarness saveFirst={saveFirst} saveSecond={saveSecond} /></BuilderLifecycleProvider>);

    fireEvent.change(screen.getByLabelText("First draft"), { target: { value: "first-latest" } });
    fireEvent.change(screen.getByLabelText("Second draft"), { target: { value: "second-latest" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    expect(saveFirst).toHaveBeenCalledWith("first-latest");
    expect(saveSecond).toHaveBeenCalledWith("second-latest");
    resolveFirst();
    await act(async () => { await Promise.resolve(); });
  });

  it("shares one per-resource drain across repeated flush requests", async () => {
    let resolveFirst!: () => void;
    const first = new Promise<void>((resolve) => { resolveFirst = resolve; });
    const save = vi.fn().mockReturnValueOnce(first).mockResolvedValue(undefined);
    render(<BuilderLifecycleProvider><ExplicitFlushHarness save={save} /></BuilderLifecycleProvider>);

    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "first" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "latest" } });
    fireEvent.click(screen.getByRole("button", { name: "Flush twice" }));

    await act(async () => { resolveFirst(); await first; });

    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith("latest");
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

  it("blocks stale conflict retries until the editor is reloaded", async () => {
    const save = vi.fn().mockRejectedValue(new ApiError("DRAFT_REVISION_CONFLICT", "Reload latest", 409));
    setup(save);
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "stale edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    expect(screen.getByText(/changed in another tab or by another admin/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload latest" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "more stale edits" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("does not classify another 409 code as a draft revision conflict", async () => {
    const save = vi.fn().mockRejectedValue(new ApiError("TEST_VERSION_IMMUTABLE", "Published", 409));
    setup(save);
    fireEvent.change(screen.getByLabelText("Draft value"), { target: { value: "edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText("Save failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reload latest" })).not.toBeInTheDocument();
  });
});
