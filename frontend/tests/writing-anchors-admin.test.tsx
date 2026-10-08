import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnchorWorkspace } from "@/features/writing-anchors/anchor-workspace";
import * as api from "@/lib/api/writing-anchors";
import { AnchorForm } from "@/features/writing-anchors/anchor-form";

vi.mock("@/lib/api/writing-anchors", async (original) => ({ ...await original<typeof import("@/lib/api/writing-anchors")>(), listAnchorSets: vi.fn(), getAnchorCoverage: vi.fn(), listAnchors: vi.fn(), listFrozenTasks: vi.fn(), createAnchorDraft: vi.fn(), createAnchor: vi.fn() }));
const set = { id: "11111111-1111-4111-8111-111111111111", name: "Human bank", version: 1, status: "DRAFT" as const, created_at: "now", activated_at: null, retired_at: null };
const task = { id: "22222222-2222-4222-8222-222222222222", test_version_id: set.id, test_title: "Fictional Writing", version_number: 2, task_number: 1 as const, task_type: "line_graph", prompt_preview: "Describe fictional data." };
const coverage = { active_set: null, production_task1: [], research_task1_ta: [], research_task2: [], recommendations: [], node_budget: 2 };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [] });
  vi.mocked(api.getAnchorCoverage).mockResolvedValue(coverage);
  vi.mocked(api.listAnchors).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 25 });
  vi.mocked(api.listFrozenTasks).mockResolvedValue({ items: [task], total: 1, offset: 0, limit: 25 });
});
describe("human Writing anchor workspace", () => {
  it("offers an empty draft workflow and separates production from research", async () => {
    render(<AnchorWorkspace />);
    expect(await screen.findByText("No anchor sets yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create draft" })).toBeEnabled();
    expect(screen.getByText("Production Task 1 · CC / LR / GRA")).toBeInTheDocument();
    expect(screen.getByText("Research · Task 1 TA and Task 2")).toBeInTheDocument();
  });
  it("uses frozen task selection and four manual labels without feedback", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Add anchor" }));
    await screen.findByText(/Fictional Writing · v2/);
    fireEvent.change(screen.getByLabelText("Frozen Writing task"), { target: { value: task.id } });
    expect(screen.getByLabelText("Task Achievement (TA)")).toBeInTheDocument();
    expect(screen.getByLabelText("Response text")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Feedback/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Response text"), { target: { value: "Intro.\n\nDetails." } });
    vi.mocked(api.createAnchor).mockRejectedValue(new Error("Draft changed; reload."));
    fireEvent.click(screen.getByRole("button", { name: "Save anchor" }));
    await waitFor(() => expect(api.createAnchor).toHaveBeenCalled());
    expect(await screen.findByRole("alert")).toHaveTextContent("Draft changed; reload.");
  });
  it("makes active banks read-only", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [{ ...set, status: "ACTIVE" }] });
    render(<AnchorWorkspace />);
    expect(await screen.findByText(/Read-only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add anchor" })).not.toBeInTheDocument();
  });
  it("ignores stale task search responses without changing the selected context", async () => {
    let late!: (value: Awaited<ReturnType<typeof api.listFrozenTasks>>) => void;
    vi.mocked(api.listFrozenTasks).mockImplementationOnce(() => new Promise(resolve => { late = resolve; })).mockResolvedValue({ items: [task], total: 1, offset: 0, limit: 25 });
    render(<AnchorForm detail={null} readOnly={false} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Search frozen tasks"), { target: { value: "new" } });
    await screen.findByText(/Fictional Writing · v2/);
    fireEvent.change(screen.getByLabelText("Frozen Writing task"), { target: { value: task.id } });
    late({ items: [{ ...task, id: set.id, test_title: "Stale task" }], total: 1, offset: 0, limit: 25 });
    await waitFor(() => expect(screen.getByLabelText("Frozen Writing task")).toHaveValue(task.id));
    expect(screen.queryByText(/Stale task/)).not.toBeInTheDocument();
  });
});
