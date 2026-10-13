import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingBenchmarkBankPage } from "@/features/writing-benchmark/bank-page";
import * as api from "@/lib/api/writing-benchmark";
import { ApiError } from "@/lib/api/client";
import { deferred, setupBenchmarkApi } from "./writing-benchmark-test-utils";
import { benchmarkSample, sampleId, otherId } from "./writing-benchmark-fixtures";

vi.mock("@/lib/api/writing-benchmark", async importOriginal => ({ ...await importOriginal<typeof api>(), getWritingBenchmarkSummary: vi.fn(), listWritingBenchmarkSamples: vi.fn(), getWritingBenchmarkSample: vi.fn(), createWritingBenchmarkSample: vi.fn(), updateWritingBenchmarkSample: vi.fn(), completeWritingBenchmarkSample: vi.fn(), deleteWritingBenchmarkSample: vi.fn(), uploadWritingBenchmarkImage: vi.fn(), removeWritingBenchmarkImage: vi.fn() }));

async function setup() { await act(async () => { render(<WritingBenchmarkBankPage />); }); }
async function settle() { await act(async () => { await Promise.resolve(); }); }

describe("durable benchmark autosave", () => {
  beforeEach(() => { vi.resetAllMocks(); setupBenchmarkApi(); vi.useFakeTimers(); });
  afterEach(() => vi.useRealTimers());

  it("debounces 1000ms, preserves exact text and advances revision", async () => {
    await setup();
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "  Local 😀\r\n\r\nEssay " } });
    await act(async () => { await vi.advanceTimersByTimeAsync(999); });
    expect(api.updateWritingBenchmarkSample).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(api.updateWritingBenchmarkSample).toHaveBeenCalledWith(sampleId, expect.objectContaining({ expected_revision: 1, essay: "  Local 😀\n\nEssay " }));
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "Second edit" } });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true }); await settle();
    expect(api.updateWritingBenchmarkSample).toHaveBeenLastCalledWith(sampleId, expect.objectContaining({ expected_revision: 2, essay: "Second edit" }));
  });

  it("keeps local content on failure and blocks selection until retry ACK", async () => {
    await setup();
    vi.mocked(api.updateWritingBenchmarkSample).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "Offline", 0));
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Keep local draft" } });
    fireEvent.click(screen.getByRole("button", { name: /T1-002/ })); await settle();
    expect(screen.getByLabelText("Prompt")).toHaveValue("Keep local draft");
    expect(api.getWritingBenchmarkSample).not.toHaveBeenCalledWith(otherId);
    fireEvent.click(screen.getByRole("button", { name: /T1-002/ })); await settle();
    expect(screen.getByLabelText("Prompt")).toHaveValue("Second fictional prompt");
  });

  it("drains later typing before selection; an A response never overwrites B", async () => {
    await setup(); const ack = deferred<api.BenchmarkSample>();
    vi.mocked(api.updateWritingBenchmarkSample).mockReturnValueOnce(ack.promise);
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "First edit" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Latest edit" } });
    fireEvent.click(screen.getByRole("button", { name: /T1-002/ })); await settle();
    expect(api.getWritingBenchmarkSample).not.toHaveBeenCalledWith(otherId);
    await act(async () => { ack.resolve(api.benchmarkSampleSchema.parse(benchmarkSample({ prompt: "First edit", revision: 2 }))); });
    expect(api.updateWritingBenchmarkSample).toHaveBeenLastCalledWith(sampleId, expect.objectContaining({ prompt: "Latest edit", expected_revision: 2 }));
    expect(screen.getByLabelText("Prompt")).toHaveValue("Second fictional prompt");
  });

  it("Ctrl+Enter waits for PATCH then Complete ACK before next persisted draft", async () => {
    await setup(); const saved = deferred<api.BenchmarkSample>(); const completed = deferred<api.BenchmarkSample>();
    vi.mocked(api.updateWritingBenchmarkSample).mockReturnValueOnce(saved.promise);
    vi.mocked(api.completeWritingBenchmarkSample).mockReturnValueOnce(completed.promise);
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "Latest essay" } });
    fireEvent.keyDown(window, { key: "Enter", metaKey: true }); await settle();
    expect(api.completeWritingBenchmarkSample).not.toHaveBeenCalled();
    await act(async () => saved.resolve(api.benchmarkSampleSchema.parse(benchmarkSample({ essay: "Latest essay", revision: 2 }))));
    expect(api.completeWritingBenchmarkSample).toHaveBeenCalledWith(sampleId, 2);
    expect(api.getWritingBenchmarkSample).not.toHaveBeenCalledWith(otherId);
    await act(async () => completed.resolve(api.benchmarkSampleSchema.parse(benchmarkSample({ essay: "Latest essay", revision: 3, status: "COMPLETE" }))));
    expect(screen.getByLabelText("Prompt")).toHaveValue("Second fictional prompt");
  });

  it("conflict preserves local form and blocks mutations until explicit reload", async () => {
    await setup();
    vi.mocked(api.updateWritingBenchmarkSample).mockRejectedValue(new ApiError("DRAFT_REVISION_CONFLICT", "Conflict", 409));
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "Unsaved local essay" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.click(screen.getByRole("button", { name: /T1-002/ })); await settle();
    expect(screen.getByLabelText("Essay")).toHaveValue("Unsaved local essay");
    expect(api.getWritingBenchmarkSample).not.toHaveBeenCalledWith(otherId);
    expect(screen.getByRole("button", { name: "Reload saved sample" })).toBeInTheDocument();
  });

  it("freezes edits during an explicitly confirmed conflict reload", async () => {
    await setup();
    vi.mocked(api.updateWritingBenchmarkSample).mockRejectedValue(new ApiError("DRAFT_REVISION_CONFLICT", "Conflict", 409));
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "Unsaved local essay" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const loaded = deferred<api.BenchmarkSample>();
    vi.mocked(api.getWritingBenchmarkSample).mockReturnValueOnce(loaded.promise);
    fireEvent.click(screen.getByRole("button", { name: "Reload saved sample" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reload saved sample" }));
    await settle();
    expect(screen.getByLabelText("Essay")).toBeDisabled();
    await act(async () => loaded.resolve(api.benchmarkSampleSchema.parse(benchmarkSample({ essay: "Saved elsewhere", revision: 9 }))));
    expect(screen.getByLabelText("Essay")).toHaveValue("Saved elsewhere");
    expect(screen.getByLabelText("Essay")).toBeEnabled();
  });
});
