import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingBenchmarkBankPage } from "@/features/writing-benchmark/bank-page";
import * as api from "@/lib/api/writing-benchmark";
import { ApiError } from "@/lib/api/client";
import { deferred, setupBenchmarkApi } from "./writing-benchmark-test-utils";
import { benchmarkSample, benchmarkSummary } from "./writing-benchmark-fixtures";

vi.mock("@/lib/api/writing-benchmark", async importOriginal => ({ ...await importOriginal<typeof api>(), getWritingBenchmarkSummary: vi.fn(), listWritingBenchmarkSamples: vi.fn(), getWritingBenchmarkSample: vi.fn(), createWritingBenchmarkSample: vi.fn(), updateWritingBenchmarkSample: vi.fn(), completeWritingBenchmarkSample: vi.fn(), deleteWritingBenchmarkSample: vi.fn(), uploadWritingBenchmarkImage: vi.fn(), removeWritingBenchmarkImage: vi.fn(), exportWritingBenchmarkBundle: vi.fn() }));

async function setup() { await act(async () => { render(<WritingBenchmarkBankPage />); }); }
async function settle() { await act(async () => { await Promise.resolve(); }); }

describe("reviewed durable benchmark export", () => {
  beforeEach(() => {
    vi.resetAllMocks(); setupBenchmarkApi(); vi.useFakeTimers();
    vi.mocked(api.exportWritingBenchmarkBundle).mockResolvedValue({ blob: new Blob(["fictional ZIP"]), filename: "writing-benchmark.zip" });
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:fictional") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it("flushes latest edit before showing fresh export summary and waits for download ACK", async () => {
    await setup(); const saved = deferred<api.BenchmarkSample>();
    vi.mocked(api.updateWritingBenchmarkSample).mockReturnValueOnce(saved.promise);
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "Latest local text" } });
    fireEvent.click(screen.getByRole("button", { name: "Export benchmark bundle" })); await settle();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.exportWritingBenchmarkBundle).not.toHaveBeenCalled();
    await act(async () => saved.resolve(api.benchmarkSampleSchema.parse(benchmarkSample({ essay: "Latest local text", revision: 2 }))));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Task 1: 0 complete, 2 draft");
    expect(dialog).toHaveTextContent("Drafts are excluded");
    expect(dialog).toHaveTextContent("DEV"); expect(dialog).toHaveTextContent("HOLDOUT");
    fireEvent.click(within(dialog).getByRole("button", { name: "Download bundle" })); await settle();
    expect(api.exportWritingBenchmarkBundle).toHaveBeenCalledOnce();
    expect(URL.createObjectURL).toHaveBeenCalledOnce(); expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fictional");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("never exports a stale snapshot after save failure and preserves local content", async () => {
    await setup(); vi.mocked(api.updateWritingBenchmarkSample).mockRejectedValue(new ApiError("NETWORK_ERROR", "Offline", 0));
    fireEvent.change(screen.getByLabelText("Essay"), { target: { value: "Keep local text" } });
    fireEvent.click(screen.getByRole("button", { name: "Export benchmark bundle" })); await settle();
    expect(api.exportWritingBenchmarkBundle).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Essay")).toHaveValue("Keep local text");
  });

  it("keeps the modal pending until ZIP ACK and blocks editor shortcuts", async () => {
    await setup();
    fireEvent.click(screen.getByRole("button", { name: "Export benchmark bundle" })); await settle();
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true }); await settle();
    expect(api.completeWritingBenchmarkSample).not.toHaveBeenCalled();
    const bundle = deferred<{ blob: Blob; filename: string }>();
    vi.mocked(api.exportWritingBenchmarkBundle).mockReturnValueOnce(bundle.promise);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Download bundle" })); await settle();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" })).toBeDisabled();
    await act(async () => bundle.resolve({ blob: new Blob(["fictional ZIP"]), filename: "writing-benchmark.zip" }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fictional");
  });

  it.each([0, 1, 100])("allows %i complete samples without quota restrictions", async count => {
    const summary = api.benchmarkSummarySchema.parse(benchmarkSummary());
    summary.tasks[0].total = count; summary.tasks[0].complete = count;
    vi.mocked(api.getWritingBenchmarkSummary).mockResolvedValue(summary);
    await setup(); fireEvent.click(screen.getByRole("button", { name: "Export benchmark bundle" })); await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent(`Task 1: ${count} complete, 0 draft`);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Download bundle" })); await settle();
    expect(api.exportWritingBenchmarkBundle).toHaveBeenCalledOnce();
  });
});
