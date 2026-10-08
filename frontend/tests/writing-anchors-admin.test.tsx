import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnchorWorkspace } from "@/features/writing-anchors/anchor-workspace";
import * as api from "@/lib/api/writing-anchors";
import { AnchorForm } from "@/features/writing-anchors/anchor-form";

vi.mock("@/lib/api/writing-anchors", async (original) => ({ ...await original<typeof import("@/lib/api/writing-anchors")>(), listAnchorSets: vi.fn(), getAnchorCoverage: vi.fn(), listAnchors: vi.fn(), listFrozenTasks: vi.fn(), createAnchorDraft: vi.fn(), createAnchor: vi.fn(), activateAnchorSet: vi.fn() }));
const set = { id: "11111111-1111-4111-8111-111111111111", name: "Human bank", version: 1, status: "DRAFT" as const, created_at: "now", activated_at: null, retired_at: null };
const task = { id: "22222222-2222-4222-8222-222222222222", test_version_id: set.id, test_title: "Fictional Writing", version_number: 2, task_number: 1 as const, task_type: "line_graph", prompt_preview: "Describe fictional data." };
const coverage = { active_set: null, production_task1: [], research_task1_ta: [], research_task2: [], recommendations: [], node_budget: 2 };

beforeEach(() => {
  vi.resetAllMocks();
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
  it.each(["coverage", "sets"])("keeps activation authoritative when refreshing %s fails", async (failedRead) => {
    const previous = { ...set, id: "33333333-3333-4333-8333-333333333333", status: "ACTIVE" as const, version: 4 };
    const draft = { ...set, version: 5 };
    const activated = { ...draft, status: "ACTIVE" as const, activated_at: "2026-10-08T00:00:00Z" };
    const row = { id: task.id, anchor_set_id: draft.id, task, word_count: 150, human_scores: { ta: 7, cc: 7, lr: 7, gra: 7 }, created_at: "2026-10-07T10:11:12Z" };
    vi.mocked(api.listAnchorSets).mockResolvedValueOnce({ items: [previous, draft] });
    vi.mocked(api.getAnchorCoverage).mockResolvedValueOnce({ ...coverage, active_set: previous });
    vi.mocked(api.listAnchors).mockResolvedValue({ items: [row], total: 1, offset: 0, limit: 25 });
    vi.mocked(api.activateAnchorSet).mockResolvedValue(activated);
    if (failedRead === "sets") vi.mocked(api.listAnchorSets).mockRejectedValue(new Error("Set refresh failed."));
    else vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [{ ...previous, status: "RETIRED" }, activated] });
    if (failedRead === "coverage") vi.mocked(api.getAnchorCoverage).mockRejectedValue(new Error("Coverage refresh failed."));
    else vi.mocked(api.getAnchorCoverage).mockResolvedValue({ ...coverage, active_set: activated });
    render(<AnchorWorkspace />);
    await screen.findByText(/Active bank: v4/);
    fireEvent.click(await screen.findByRole("button", { name: "Activate draft" }));
    await screen.findByRole("alert");
    expect(screen.getByText(/Read-only active version/)).toBeInTheDocument();
    for (const name of ["Add anchor", "Activate draft", "Delete", "View / edit"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/Active bank: v4/)).not.toBeInTheDocument();
    if (failedRead === "coverage") expect(screen.getByText(/Active coverage unavailable/)).toBeInTheDocument();
    else expect(screen.getByText(/Active bank: v5/)).toBeInTheDocument();
  });
  it("shows all half-band counts, comparison costs and anchor creation dates", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    vi.mocked(api.getAnchorCoverage).mockResolvedValue({ ...coverage, production_task1: [{ criterion: "cc", counts: { "4.5": 2, "6.5": 3, "7": 1 }, ladder: [], readiness: "PARTIAL", pilot_complete: false }] });
    vi.mocked(api.listAnchors).mockResolvedValue({ items: [{ id: task.id, anchor_set_id: set.id, task, word_count: 150, human_scores: { ta: 7, cc: 7, lr: 7, gra: 7 }, created_at: "2026-10-07T10:11:12Z" }], total: 1, offset: 0, limit: 25 });
    render(<AnchorWorkspace />);
    const counts = await screen.findByRole("group", { name: "CC label counts" });
    expect(within(counts).getByText(/4.5: 2/)).toBeInTheDocument();
    expect(within(counts).getByText(/6.5: 3/)).toBeInTheDocument();
    expect(screen.getByText(/2 comparisons per node/)).toBeInTheDocument();
    expect(screen.getByText(/12 comparisons per Task 1 run/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Created" })).toBeInTheDocument();
    expect(await screen.findByText("2026-10-07")).toBeInTheDocument();
  });
});
