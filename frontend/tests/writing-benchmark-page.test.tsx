import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Page from "@/app/admin/writing-benchmark/page";
import * as api from "@/lib/api/writing-benchmark";
import { ApiError } from "@/lib/api/client";
import { benchmarkSummary } from "./writing-benchmark-fixtures";
import { setupBenchmarkApi } from "./writing-benchmark-test-utils";
import { renderWithLocale } from "./locale-test-utils";

const auth = vi.hoisted(() => ({ role: "ADMIN" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/writing-benchmark", useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { role: auth.role }, loading: false, sessionError: null }) }));
vi.mock("@/lib/api/writing-benchmark", async importOriginal => ({ ...await importOriginal<typeof api>(), getWritingBenchmarkSummary: vi.fn(), listWritingBenchmarkSamples: vi.fn(), getWritingBenchmarkSample: vi.fn(), createWritingBenchmarkSample: vi.fn(), updateWritingBenchmarkSample: vi.fn(), completeWritingBenchmarkSample: vi.fn(), deleteWritingBenchmarkSample: vi.fn(), uploadWritingBenchmarkImage: vi.fn(), removeWritingBenchmarkImage: vi.fn() }));

describe("Writing benchmark master/detail", () => {
  beforeEach(() => { vi.resetAllMocks(); window.localStorage.clear(); auth.role = "ADMIN"; setupBenchmarkApi(); });

  it.each(["USER", "TEACHER"])("denies %s before loading private bank", role => {
    auth.role = role; renderWithLocale(<Page />);
    expect(screen.getByRole("heading", { name: "Forbidden" })).toBeInTheDocument();
    expect(api.getWritingBenchmarkSummary).not.toHaveBeenCalled();
  });

  it("shows stable codes and one editor, loads persisted selection and Task 2 TR fields", async () => {
    renderWithLocale(<Page />);
    await screen.findByLabelText("Prompt");
    expect(screen.getAllByLabelText("Essay")).toHaveLength(1);
    expect(screen.getByRole("tab", { name: /Task 1/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: /T1-002/ }));
    await waitFor(() => expect(screen.getByLabelText("Prompt")).toHaveValue("Second fictional prompt"));
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    await waitFor(() => expect(screen.getByRole("tab", { name: /Task 2/ })).toHaveAttribute("aria-selected", "true"));
    fireEvent.click(screen.getByRole("button", { name: "New sample" }));
    await screen.findByLabelText("Task Response (TR)");
    expect(screen.queryByLabelText("Task Achievement (TA)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Task 1 image")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/feedback/i)).not.toBeInTheDocument();
  });

  it("localizes current form without losing edits or reloading", async () => {
    renderWithLocale(<Page />); const prompt = await screen.findByLabelText("Prompt");
    fireEvent.change(prompt, { target: { value: "Fictional local draft 😀" } });
    const reads = vi.mocked(api.getWritingBenchmarkSample).mock.calls.length;
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByLabelText("Đề bài")).toBe(prompt);
    expect(prompt).toHaveValue("Fictional local draft 😀");
    expect(api.getWritingBenchmarkSample).toHaveBeenCalledTimes(reads);
  });

  it("uses controlled half bands and production essay mean rounding", async () => {
    renderWithLocale(<Page />); await screen.findByLabelText("Prompt");
    for (const [label, value] of [["Task Achievement (TA)", "6"], ["Coherence and Cohesion (CC)", "6"], ["Lexical Resource (LR)", "6.5"], ["Grammatical Range and Accuracy (GRA)", "6.5"]]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(screen.getByLabelText("Derived overall")).toHaveTextContent("6.5");
    expect(screen.getByLabelText("Task Achievement (TA)").querySelectorAll("option")).toHaveLength(20);
  });

  it("counts drafts toward capacity and supports keyboard tab navigation", async () => {
    const summary = api.benchmarkSummarySchema.parse(benchmarkSummary());
    summary.tasks[0].total = 100; summary.tasks[0].draft = 100;
    vi.mocked(api.getWritingBenchmarkSummary).mockResolvedValue(summary);
    renderWithLocale(<Page />); await screen.findByLabelText("Prompt");
    expect(screen.getByRole("button", { name: "New sample" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("tab", { name: /Task 1/ }), { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByRole("tab", { name: /Task 2/ })).toHaveAttribute("aria-selected", "true"));
    expect(screen.getByRole("button", { name: "New sample" })).toBeEnabled();
  });

  it("associates safe completion issues with required fields", async () => {
    vi.mocked(api.completeWritingBenchmarkSample).mockRejectedValue(new ApiError("BENCHMARK_INCOMPLETE", "Missing fields", 422, { errors: [{ path: "prompt", message: "Required" }, { path: "human_scores.ta", message: "Required" }] }));
    renderWithLocale(<Page />); await screen.findByLabelText("Prompt");
    fireEvent.click(screen.getByRole("button", { name: "Complete sample" }));
    await waitFor(() => expect(screen.getByLabelText("Prompt")).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByLabelText("Task Achievement (TA)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Essay")).toBeEnabled();
  });

  it("uploads and previews private image, then confirms removal and deletion", async () => {
    renderWithLocale(<Page />); await screen.findByLabelText("Prompt");
    const file = new File(["fictional"], "fictional.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Task 1 image"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload image" }));
    await screen.findByAltText("Task 1 image preview");
    expect(screen.getByAltText("Task 1 image preview")).toHaveAttribute("src", expect.stringContaining("/image?revision=2"));
    fireEvent.click(screen.getByRole("button", { name: "Remove image" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove image" }));
    await waitFor(() => expect(api.removeWritingBenchmarkImage).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Delete sample" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete sample" }));
    await waitFor(() => expect(api.deleteWritingBenchmarkSample).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByLabelText("Prompt")).toHaveValue("Second fictional prompt"));
    expect(screen.getByRole("button", { name: "New sample" })).toBeEnabled();
  });
});
