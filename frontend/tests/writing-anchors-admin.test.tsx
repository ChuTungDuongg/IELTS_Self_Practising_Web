import { readFileSync } from "node:fs";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WritingAnchorsPage from "@/app/admin/writing-anchors/page";
import { AnchorWorkspace } from "@/features/writing-anchors/anchor-workspace";
import { AnchorForm } from "@/features/writing-anchors/anchor-form";
import { AnchorCoveragePanel } from "@/features/writing-anchors/anchor-coverage";
import styles from "@/features/writing-anchors/anchor-workspace.module.css";
import * as api from "@/lib/api/writing-anchors";

vi.mock("@/lib/api/writing-anchors", async (original) => ({
  ...await original<typeof import("@/lib/api/writing-anchors")>(),
  listAnchorSets: vi.fn(), getAnchorCoverage: vi.fn(), listAnchors: vi.fn(),
  listFrozenTasks: vi.fn(), getAnchor: vi.fn(), createAnchorDraft: vi.fn(),
  createAnchor: vi.fn(), updateAnchor: vi.fn(), deleteAnchor: vi.fn(), activateAnchorSet: vi.fn(),
}));
const set: api.AnchorSet = { id: "11111111-1111-4111-8111-111111111111", name: "Human bank", version: 1, status: "DRAFT", created_at: "now", activated_at: null, retired_at: null };
const task: api.FrozenTask = { id: "22222222-2222-4222-8222-222222222222", test_version_id: set.id, test_title: "Fictional Writing", version_number: 2, task_number: 1, task_type: "line_graph", prompt_preview: "Describe fictional data." };
const detail: api.AnchorDetail = { id: "44444444-4444-4444-8444-444444444444", anchor_set_id: set.id, task, word_count: 150, human_scores: { ta: 6.5, cc: 7, lr: 7, gra: 7 }, created_at: "2026-10-07T10:11:12Z", response_text: "Intro.\n\nDetails.", admin_note: null, provenance: null };
const emptyRow = (criterion: "cc" | "lr" | "gra"): api.AnchorCoverage["production_task1"][number] => ({ criterion, counts: {}, ladder: [], readiness: "EMPTY", pilot_complete: false });
const coverage: api.AnchorCoverage = { active_set: null, production_task1: [emptyRow("cc"), emptyRow("lr"), emptyRow("gra")], research_task1_ta: [], research_task2: [], recommendations: [], node_budget: 2 };
const emptyPage = { items: [], total: 0, offset: 0, limit: 25 };
const input = { writing_task_id: task.id, response_text: detail.response_text, human_scores: detail.human_scores, admin_note: null, provenance: null };
const bank = () => screen.getByRole("region", { name: "Bộ dữ liệu anchor" });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [] });
  vi.mocked(api.getAnchorCoverage).mockResolvedValue(coverage);
  vi.mocked(api.listAnchors).mockResolvedValue(emptyPage);
  vi.mocked(api.listFrozenTasks).mockResolvedValue({ items: [task], total: 1, offset: 0, limit: 25 });
  vi.mocked(api.getAnchor).mockResolvedValue(detail);
  vi.mocked(api.createAnchorDraft).mockResolvedValue(set);
  vi.mocked(api.createAnchor).mockResolvedValue(detail);
  vi.mocked(api.updateAnchor).mockResolvedValue(detail);
  vi.mocked(api.deleteAnchor).mockResolvedValue(undefined);
});

describe("Vietnamese Writing anchor workflow", () => {
  it("introduces the page in Vietnamese and offers an empty draft workflow", async () => {
    render(<WritingAnchorsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Kho bài Writing đã chấm bởi người" })).toBeInTheDocument();
    expect(screen.getByText("Quản lý các bài Writing đã được chấm thủ công để làm dữ liệu tham chiếu cho hệ thống chấm AI.")).toBeInTheDocument();
    expect(await screen.findByText("Chưa có bộ dữ liệu anchor. Tạo bản nháp để bắt đầu.")).toBeInTheDocument();
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    fireEvent.click(screen.getByRole("button", { name: "Tạo bản nháp" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Thêm bài tham chiếu" })).toBeEnabled());
    expect(api.createAnchorDraft).toHaveBeenCalledExactlyOnceWith();
    expect(within(bank()).getByText("Bản nháp v1")).toBeInTheDocument();
    expect(within(bank()).getByText("Đang chỉnh sửa")).toBeInTheDocument();
  });

  it("shows a useful Vietnamese draft empty state and keeps filter enum values unchanged", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    render(<AnchorWorkspace />);
    expect(await screen.findByText("Chưa có bài tham chiếu phù hợp với bộ lọc hiện tại.")).toBeInTheDocument();
    expect(screen.getByText("Hãy thêm các bài Writing đã được chấm thủ công để bắt đầu xây dựng bộ anchor.")).toBeInTheDocument();
    expect(screen.getByText("0 bài")).toBeInTheDocument();
    const status = screen.getByLabelText("Trạng thái");
    for (const [value, label] of [["DRAFT", "Bản nháp"], ["ACTIVE", "Đang sử dụng"], ["RETIRED", "Đã lưu trữ"]]) {
      expect(within(status).getByRole("option", { name: label })).toHaveValue(value);
    }
    fireEvent.change(status, { target: { value: "ACTIVE" } });
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ status: "ACTIVE" })));
    expect(screen.queryByText("Hãy thêm các bài Writing đã được chấm thủ công để bắt đầu xây dựng bộ anchor.")).not.toBeInTheDocument();
  });

  it("adds four human labels, preserving paragraphs and the existing payload without feedback", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Thêm bài tham chiếu" }));
    await screen.findByText(/Fictional Writing · v2/);
    fireEvent.change(screen.getByLabelText("Đề Writing đã xuất bản"), { target: { value: task.id } });
    expect(screen.getByLabelText("Task Achievement (TA)")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Feedback|Phản hồi/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Bài viết của học viên"), { target: { value: detail.response_text } });
    fireEvent.change(screen.getByLabelText("Task Achievement (TA)"), { target: { value: "6.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(api.createAnchor).toHaveBeenCalledExactlyOnceWith(set.id, input));
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
  });

  it("keeps the form available when saving fails", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    vi.mocked(api.createAnchor).mockRejectedValue(new Error("Bản nháp đã thay đổi. Hãy làm mới."));
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Thêm bài tham chiếu" }));
    await screen.findByText(/Fictional Writing · v2/);
    fireEvent.change(screen.getByLabelText("Đề Writing đã xuất bản"), { target: { value: task.id } });
    fireEvent.change(screen.getByLabelText("Bài viết của học viên"), { target: { value: detail.response_text } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bản nháp đã thay đổi. Hãy làm mới.");
    expect(screen.getByRole("button", { name: "Lưu bài tham chiếu" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("edits and deletes draft entries through the existing API workflows", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 1 });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem / chỉnh sửa" }));
    expect(await screen.findByRole("heading", { name: "Chỉnh sửa bài tham chiếu" })).toBeInTheDocument();
    expect(api.getAnchor).toHaveBeenCalledExactlyOnceWith(detail.id);
    fireEvent.change(screen.getByLabelText("Ghi chú nội bộ"), { target: { value: "Đã kiểm tra" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(api.updateAnchor).toHaveBeenCalledExactlyOnceWith(detail.id, { ...input, admin_note: "Đã kiểm tra" }));
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
    vi.mocked(api.listAnchors).mockResolvedValue(emptyPage);
    fireEvent.click(await screen.findByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(api.deleteAnchor).toHaveBeenCalledExactlyOnceWith(detail.id));
    expect(await screen.findByText("0 bài")).toBeInTheDocument();
  });

  it.each(["ACTIVE", "RETIRED"] as const)("keeps %s versions read-only with Vietnamese actions", async (status) => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [{ ...set, status }] });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 1 });
    render(<AnchorWorkspace />);
    expect(await screen.findByText("Phiên bản này chỉ đọc. Tạo hoặc chọn bản nháp để chỉnh sửa.")).toBeInTheDocument();
    expect(within(bank()).getByText("Chỉ đọc")).toBeInTheDocument();
    expect(within(bank()).getByRole("button", { name: status === "ACTIVE" ? "Tạo bản nháp mới từ bản đang dùng" : "Tạo bản nháp" })).toBeEnabled();
    for (const name of ["Thêm bài tham chiếu", "Kích hoạt bản nháp", "Xóa", "Xem / chỉnh sửa"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    fireEvent.click(await screen.findByRole("button", { name: "Xem" }));
    expect(await screen.findByRole("heading", { name: "Xem bài tham chiếu" })).toBeInTheDocument();
    expect(screen.getByLabelText("Bài viết của học viên")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Lưu bài tham chiếu" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("creates a draft from the active bank without changing the lifecycle API", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    const draft = { ...set, id: task.id, version: 2 };
    vi.mocked(api.listAnchorSets).mockResolvedValueOnce({ items: [active] }).mockResolvedValue({ items: [active, draft] });
    vi.mocked(api.createAnchorDraft).mockResolvedValue(draft);
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Tạo bản nháp mới từ bản đang dùng" }));
    expect(await screen.findByText("Bản nháp v2")).toBeInTheDocument();
    expect(api.createAnchorDraft).toHaveBeenCalledExactlyOnceWith();
    expect(within(bank()).getByLabelText("Phiên bản")).toHaveValue(draft.id);
  });

  it("opens the draft from the zero-coverage CTA even while viewing an active version", async () => {
    const active = { ...set, id: "33333333-3333-4333-8333-333333333333", status: "ACTIVE" as const };
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [active, set] });
    vi.mocked(api.getAnchorCoverage).mockResolvedValue({ ...coverage, active_set: active });
    render(<AnchorWorkspace />);
    await screen.findByText("Bản nháp v1");
    fireEvent.change(within(bank()).getByLabelText("Phiên bản"), { target: { value: active.id } });
    fireEvent.click(screen.getByRole("button", { name: "Thêm bài tham chiếu vào bản nháp" }));
    expect(within(bank()).getByLabelText("Phiên bản")).toHaveValue(set.id);
    expect(screen.getByRole("heading", { name: "Thêm bài tham chiếu" })).toBeInTheDocument();
    expect(screen.getByLabelText("Bài viết của học viên")).toBeEnabled();
  });

  it("keeps task, search and pagination filters functional and displays creation dates", async () => {
    vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [set] });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 26 });
    render(<AnchorWorkspace />);
    expect(await screen.findByText("2026-10-07")).toBeInTheDocument();
    for (const heading of ["Đề Writing", "Số từ", "TA / TR", "CC", "LR", "GRA", "Ngày thêm", "Thao tác"]) {
      expect(screen.getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
    fireEvent.change(screen.getByLabelText("Kỹ năng"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Tìm bài tham chiếu"), { target: { value: "fictional" } });
    fireEvent.change(screen.getByLabelText("Dạng bài"), { target: { value: "line_graph" } });
    fireEvent.change(screen.getByLabelText("Đề Writing"), { target: { value: task.id } });
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ task_number: 2, search: "fictional", task_type: "line_graph", writing_task_id: task.id, offset: 0 })));
    fireEvent.click(screen.getByRole("button", { name: "Sau" }));
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })));
    fireEvent.click(screen.getByRole("button", { name: "Trước" }));
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 })));
    fireEvent.click(screen.getByRole("button", { name: "Làm mới" }));
    await waitFor(() => expect(api.listAnchorSets).toHaveBeenCalledTimes(2));
  });

  it.each(["coverage", "sets"])("keeps activation authoritative when refreshing %s fails", async (failedRead) => {
    const previous = { ...set, id: "33333333-3333-4333-8333-333333333333", status: "ACTIVE" as const, version: 4 };
    const draft = { ...set, version: 5 };
    const activated = { ...draft, status: "ACTIVE" as const, activated_at: "2026-10-08T00:00:00Z" };
    vi.mocked(api.listAnchorSets).mockResolvedValueOnce({ items: [previous, draft] });
    vi.mocked(api.getAnchorCoverage).mockResolvedValueOnce({ ...coverage, active_set: previous });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 1 });
    vi.mocked(api.activateAnchorSet).mockResolvedValue(activated);
    if (failedRead === "sets") vi.mocked(api.listAnchorSets).mockRejectedValue(new Error("Không thể làm mới phiên bản."));
    else vi.mocked(api.listAnchorSets).mockResolvedValue({ items: [{ ...previous, status: "RETIRED" }, activated] });
    if (failedRead === "coverage") vi.mocked(api.getAnchorCoverage).mockRejectedValue(new Error("Không thể làm mới mức sẵn sàng."));
    else vi.mocked(api.getAnchorCoverage).mockResolvedValue({ ...coverage, active_set: activated });
    render(<AnchorWorkspace />);
    await within(bank()).findByText("v4", { exact: true });
    fireEvent.click(await screen.findByRole("button", { name: "Kích hoạt bản nháp" }));
    await screen.findByRole("alert");
    expect(api.activateAnchorSet).toHaveBeenCalledExactlyOnceWith(draft.id);
    expect(screen.getByText("Phiên bản này chỉ đọc. Tạo hoặc chọn bản nháp để chỉnh sửa.")).toBeInTheDocument();
    for (const name of ["Thêm bài tham chiếu", "Kích hoạt bản nháp", "Xóa", "Xem / chỉnh sửa"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(within(bank()).queryByText("v4", { exact: true })).not.toBeInTheDocument();
    if (failedRead === "coverage") {
      expect(screen.getByText("Không thể tải mức độ sẵn sàng. Hãy làm mới để thử lại.")).toBeInTheDocument();
      expect(within(bank()).getByText("Chưa xác định")).toBeInTheDocument();
    } else expect(within(bank()).getByText("v5", { exact: true })).toBeInTheDocument();
  });
});

describe("human anchor form validation", () => {
  it("ignores stale task search responses without changing the selected context", async () => {
    let late!: (value: Awaited<ReturnType<typeof api.listFrozenTasks>>) => void;
    vi.mocked(api.listFrozenTasks).mockImplementationOnce(() => new Promise(resolve => { late = resolve; })).mockResolvedValue({ items: [task], total: 1, offset: 0, limit: 25 });
    render(<AnchorForm detail={null} readOnly={false} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Tìm đề Writing"), { target: { value: "new" } });
    await screen.findByText(/Fictional Writing · v2/);
    fireEvent.change(screen.getByLabelText("Đề Writing đã xuất bản"), { target: { value: task.id } });
    late({ items: [{ ...task, id: set.id, test_title: "Stale task" }], total: 1, offset: 0, limit: 25 });
    await waitFor(() => expect(screen.getByLabelText("Đề Writing đã xuất bản")).toHaveValue(task.id));
    expect(screen.queryByText(/Stale task/)).not.toBeInTheDocument();
  });

  it.each([
    { field: "task", value: "", message: "Vui lòng chọn đề Writing đã xuất bản." },
    { field: "response", value: " \n ", message: "Vui lòng nhập bài viết của học viên (không chỉ khoảng trắng)." },
    ...["", "6.2", "-0.5", "9.5"].map(value => ({ field: "score", value, message: "Vui lòng chọn đề Writing, nhập bài viết và đủ 4 điểm tiêu chí hợp lệ theo bước 0.5 từ 0 đến 9." })),
  ])("rejects invalid $field '$value' with specific Vietnamese validation", async ({ field, value, message }) => {
    const onSave = vi.fn();
    render(<AnchorForm detail={detail} readOnly={false} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    if (field === "task") fireEvent.change(screen.getByLabelText("Đề Writing đã xuất bản"), { target: { value } });
    if (field === "response") fireEvent.change(screen.getByLabelText("Bài viết của học viên"), { target: { value } });
    if (field === "score") fireEvent.change(screen.getByLabelText("CC"), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("accepts band boundaries and maps Task 2 TR to the unchanged ta field", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<AnchorForm detail={{ ...detail, task: { ...task, task_number: 2 } }} readOnly={false} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    expect(screen.queryByLabelText("Task Achievement (TA)")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Task Response (TR)"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("CC"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("LR"), { target: { value: "6.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledExactlyOnceWith({ ...input, human_scores: { ta: 0, cc: 9, lr: 6.5, gra: 7 } }));
  });
});

describe("anchor readiness and progressive disclosure", () => {
  it("states the scoring architecture and Direct fallback before empty counts", () => {
    const onAdd = vi.fn();
    render(<AnchorCoveragePanel coverage={coverage} onAddAnchor={onAdd} />);
    expect(screen.getByText(/TA không dùng anchor/)).toHaveTextContent("luôn được chấm trực tiếp bằng Direct dựa trên biểu đồ/hình ảnh");
    expect(screen.getByText(/dùng TACS \(so sánh với bài tham chiếu\)/)).toHaveTextContent("khi đủ anchor; nếu chưa đủ, hệ thống tự dùng Direct");
    expect(screen.getByText(/hiện vẫn dùng MTS\. Anchor Task 2/)).toHaveTextContent("TR / CC / LR / GRA");
    const empty = screen.getByText("Chưa có bộ anchor đang hoạt động.");
    expect(screen.getByText("CC, LR và GRA hiện sẽ tự động dùng Direct scoring.")).toBeInTheDocument();
    expect(empty.compareDocumentPosition(screen.getByRole("article", { name: "Mức sẵn sàng CC" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Thêm bài tham chiếu vào bản nháp" }));
    expect(onAdd).toHaveBeenCalledOnce();
    const target = screen.getByRole("region", { name: "Mục tiêu nên bắt đầu" });
    expect(within(target).getByText("Cho từng tiêu chí CC, LR và GRA:")).toBeInTheDocument();
    for (const band of [6, 7, 8]) expect(within(target).getByText("Band " + band).parentElement).toHaveTextContent("khoảng 2 bài");
    expect(within(target).getByText(/Band 5 và Band 9, khoảng 3 bài/)).toBeInTheDocument();
  });

  it.each([
    ["EMPTY", "Chưa có dữ liệu"], ["PARTIAL", "Chưa đủ anchor"],
    ["PAIRWISE_USABLE", "Có thể dùng TACS"], ["RECOMMENDED_COVERAGE", "Đã đạt mức khuyến nghị"],
  ] as const)("presents %s as %s without exposing its enum in the readiness card", (readiness, label) => {
    render(<AnchorCoveragePanel coverage={{ ...coverage, active_set: { ...set, status: "ACTIVE" }, production_task1: [{ ...emptyRow("cc"), readiness }] }} />);
    const card = screen.getByRole("article", { name: "Mức sẵn sàng CC" });
    expect(within(card).getByText(label)).toBeInTheDocument();
    expect(card).not.toHaveTextContent(readiness);
    expect(within(card).getByText(readiness === "PAIRWISE_USABLE" || readiness === "RECOMMENDED_COVERAGE" ? "Chấm bằng TACS" : "Tự động dùng Direct")).toBeInTheDocument();
  });

  it("keeps exact Band 5–9 counts and the usable ladder for every language criterion", () => {
    const rows: api.AnchorCoverage["production_task1"] = [
      { criterion: "cc", counts: { "5": 1, "6": 2, "7": 3, "8": 4, "9": 5, "6.5": 20 }, ladder: [5, 6, 7, 8, 9], readiness: "PAIRWISE_USABLE", pilot_complete: true },
      { criterion: "lr", counts: { "5": 6, "6": 7, "7": 8, "8": 9, "9": 10 }, ladder: [5, 6, 7, 8, 9], readiness: "RECOMMENDED_COVERAGE", pilot_complete: true },
      { criterion: "gra", counts: { "6.5": 3 }, ladder: [], readiness: "PARTIAL", pilot_complete: false },
    ];
    render(<AnchorCoveragePanel coverage={{ ...coverage, active_set: { ...set, status: "ACTIVE" }, production_task1: rows }} />);
    for (const row of rows) {
      const card = screen.getByRole("article", { name: "Mức sẵn sàng " + row.criterion.toUpperCase() });
      for (const band of [5, 6, 7, 8, 9]) {
        const cell = within(card).getByText("Band " + band).parentElement!;
        expect(within(cell).getByRole("definition")).toHaveTextContent(String(row.counts[String(band)] ?? 0));
      }
      expect(within(card).getByText("Dải band có thể dùng")).toBeInTheDocument();
      expect(within(card).getByText(row.ladder.join(" → ") || "Chưa có")).toBeInTheDocument();
    }
  });

  it.each([2, 3])("keeps technical and research sections closed, preserving half-bands and a %s-node cost bound", (nodeBudget) => {
    render(<AnchorCoveragePanel coverage={{ ...coverage, node_budget: nodeBudget, production_task1: [{ ...emptyRow("cc"), counts: { "4.5": 2, "6.5": 3, "7": 1 }, readiness: "PARTIAL" }], recommendations: ["Technical minimum: one human anchor at two adjacent whole bands.", "Initial practical target: 20–30 carefully human-labelled Task 1 responses; similar Task 2 data later.", "Recommendations are operational guidance, not IELTS rules or statistical guarantees."] }} />);
    const technical = screen.getByRole("group", { name: "Chi tiết kỹ thuật" });
    const research = screen.getByRole("group", { name: "Dữ liệu nghiên cứu" });
    expect(technical).not.toHaveAttribute("open");
    expect(research).not.toHaveAttribute("open");
    for (const table of screen.queryAllByRole("table")) expect(table).not.toBeVisible();
    fireEvent.click(within(technical).getByText("Chi tiết kỹ thuật", { selector: "summary" }));
    expect(technical).toHaveAttribute("open");
    expect(within(technical).getByText(nodeBudget * 2 + " lượt so sánh cho mỗi tiêu chí ngôn ngữ")).toBeInTheDocument();
    expect(within(technical).getByText(nodeBudget * 6 + " lượt cho một bài Task 1")).toBeInTheDocument();
    expect(within(technical).getByText(/thứ tự đảo ngược/)).toBeInTheDocument();
    expect(within(technical).getByText(/không phải số đo độ trễ thực tế/)).toBeInTheDocument();
    const table = within(technical).getByRole("table", { name: "Task 1 · Số bài theo từng band (gồm điểm nửa band)" });
    const cells = within(within(table).getByRole("row", { name: /^CC / })).getAllByRole("cell");
    expect(cells[9]).toHaveTextContent("2");
    expect(cells[13]).toHaveTextContent("3");
    expect(within(technical).getByText(/Mức tối thiểu kỹ thuật/)).toBeInTheDocument();
    expect(within(technical).getByText(/20–30 bài Task 1/)).toBeInTheDocument();
    expect(within(technical).getByText(/Bản nháp ít dữ liệu vẫn có thể kích hoạt/)).toBeInTheDocument();
    expect(within(technical).queryByText(/Technical minimum:/)).not.toBeInTheDocument();
  });

  it("renders structured Task 1 TA and Task 2 research grids with MTS explained and all bands retained", () => {
    const counts = { "0": 2, "4.5": 1, "5": 3, "5.5": 4, "6.5": 5, "9": 6 };
    const { container } = render(<AnchorCoveragePanel coverage={{ ...coverage, research_task1_ta: [{ ...emptyRow("cc"), criterion: "ta", task, counts }], research_task2: [{ ...emptyRow("cc"), criterion: "ta", counts }, { ...emptyRow("cc"), counts }] }} />);
    const research = screen.getByRole("group", { name: "Dữ liệu nghiên cứu" });
    fireEvent.click(within(research).getByText("Dữ liệu nghiên cứu", { selector: "summary" }));
    expect(within(research).getByText(/Production Task 1 không dùng TA anchor để chấm/)).toBeInTheDocument();
    expect(within(research).getByText(/Task 2 hiện vẫn dùng MTS cho TR, CC, LR và GRA/)).toBeInTheDocument();
    const table = within(research).getByRole("table", { name: "Task 2 · Số bài theo tiêu chí" });
    for (const band of [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9]) expect(within(table).getByRole("columnheader", { name: "Band " + band })).toBeInTheDocument();
    const tr = within(within(table).getByRole("row", { name: /^TR / })).getAllByRole("cell");
    expect(tr[0]).toHaveTextContent("3");
    expect(tr[1]).toHaveTextContent("4");
    expect(tr[3]).toHaveTextContent("5");
    expect(tr[8]).toHaveTextContent("6");
    expect(within(research).getByRole("table", { name: "Task 1 · TA theo đề Writing" })).toHaveTextContent("Fictional Writing · v2 · TA");
    for (const paragraph of container.querySelectorAll("p")) expect(paragraph.textContent).not.toMatch(/\d(?:\.\d)?: \d+,/);
    fireEvent.click(within(research).getByText("Các band khác (0–4.5)", { selector: "summary" }));
    const other = within(research).getByRole("table", { name: "Task 2 · Số bài ở Band 0–4.5" });
    const otherCells = within(within(other).getByRole("row", { name: /^TR / })).getAllByRole("cell");
    expect(otherCells[0]).toHaveTextContent("2");
    expect(otherCells[9]).toHaveTextContent("1");
  });

  it("does not claim empty coverage or show stale readiness when coverage is unavailable", () => {
    render(<AnchorCoveragePanel coverage={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Không thể tải mức độ sẵn sàng. Hãy làm mới để thử lại.");
    expect(screen.queryByText("Chưa có bộ anchor đang hoạt động.")).not.toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("uses responsive layout classes, keyboard-scrollable tables and existing dark-mode tokens", () => {
    const { container } = render(<div className={styles.workspace}><AnchorCoveragePanel coverage={coverage} /></div>);
    expect(screen.getByRole("article", { name: "Mức sẵn sàng CC" }).parentElement).toHaveClass(styles.readinessGrid);
    expect(screen.getByRole("region", { name: "Mục tiêu nên bắt đầu" })).toHaveClass(styles.target);
    const scrollRegion = container.querySelector('[aria-label="Task 1 · Số bài theo từng band (gồm điểm nửa band)"]');
    expect(scrollRegion).toHaveClass(styles.overflow);
    expect(scrollRegion).toHaveAttribute("tabindex", "0");
    const css = readFileSync("src/features/writing-anchors/anchor-workspace.module.css", "utf8");
    expect(css).toMatch(/@media \(max-width: 960px\).*\.readinessGrid \{ grid-template-columns: 1fr; \}/);
    expect(css).toMatch(/@media \(max-width: 640px\)/);
    expect(css).toMatch(/\.filters, \.formFilters \{ grid-template-columns: 1fr; \}/);
    for (const token of ["--surface", "--surface-soft", "--ink", "--ink-soft", "--line", "--accent-soft"]) expect(css).toContain("var(" + token + ")");
    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
  });
});
