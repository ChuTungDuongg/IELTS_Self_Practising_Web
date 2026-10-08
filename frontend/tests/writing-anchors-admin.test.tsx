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
  getAnchorBank: vi.fn(), editAnchorBank: vi.fn(), applyAnchorBank: vi.fn(), cancelAnchorBank: vi.fn(), deleteAnchorBank: vi.fn(), getAnchorHistory: vi.fn(), getAnchorCoverage: vi.fn(), listAnchors: vi.fn(),
  listFrozenTasks: vi.fn(), getAnchor: vi.fn(), createAnchorDraft: vi.fn(),
  createAnchor: vi.fn(), updateAnchor: vi.fn(), deleteAnchor: vi.fn(), activateAnchorSet: vi.fn(),
}));
const set: api.AnchorSet = { id: "11111111-1111-4111-8111-111111111111", name: "Human bank", version: 1, status: "DRAFT", created_at: "now", activated_at: null, retired_at: null };
const task: api.FrozenTask = { id: "22222222-2222-4222-8222-222222222222", test_version_id: set.id, test_title: "Fictional Writing", version_number: 2, task_number: 1, task_type: "line_graph", prompt_preview: "Describe fictional data." };
const detail: api.AnchorDetail = { id: "44444444-4444-4444-8444-444444444444", anchor_set_id: set.id, source_kind: "BUILDER_TASK", custom_prompt: null, task, word_count: 150, human_scores: { ta: 6.5, cc: 7, lr: 7, gra: 7 }, created_at: "2026-10-07T10:11:12Z", response_text: "Intro.\n\nDetails.", admin_note: null, provenance: null };
const emptyRow = (criterion: "cc" | "lr" | "gra"): api.AnchorCoverage["production_task1"][number] => ({ criterion, counts: {}, ladder: [], readiness: "EMPTY", pilot_complete: false });
const coverage: api.AnchorCoverage = { active_set: null, production_task1: [emptyRow("cc"), emptyRow("lr"), emptyRow("gra")], research_task1_ta: [], research_task2: [], recommendations: [], node_budget: 2 };
const emptyPage = { items: [], total: 0, offset: 0, limit: 25 };
const input = { source_kind: "BUILDER_TASK" as const, writing_task_id: task.id, response_text: detail.response_text, human_scores: detail.human_scores, admin_note: null, provenance: null };
const noBank: api.AnchorBankState = { current: null, working: null, current_count: 0, working_count: 0 };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getAnchorBank).mockResolvedValue(noBank);
  vi.mocked(api.editAnchorBank).mockResolvedValue(set);
  vi.mocked(api.getAnchorHistory).mockResolvedValue({ items: [] });
  vi.mocked(api.getAnchorCoverage).mockResolvedValue(coverage);
  vi.mocked(api.listAnchors).mockResolvedValue(emptyPage);
  vi.mocked(api.listFrozenTasks).mockResolvedValue({ items: [task], total: 1, offset: 0, limit: 25 });
  vi.mocked(api.getAnchor).mockResolvedValue(detail);
  vi.mocked(api.createAnchorDraft).mockResolvedValue(set);
  vi.mocked(api.createAnchor).mockResolvedValue(detail);
  vi.mocked(api.updateAnchor).mockResolvedValue(detail);
  vi.mocked(api.deleteAnchor).mockResolvedValue(undefined);
});

describe("logical current Writing anchor bank", () => {
  it("shows the Vietnamese page heading, Direct no-bank state and creates a working bank", async () => {
    render(<WritingAnchorsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Kho bài Writing đã chấm bởi người" })).toBeInTheDocument();
    expect(await screen.findByText("Chưa có bộ anchor đang dùng.")).toBeInTheDocument();
    expect(screen.getByText("CC, LR và GRA hiện sử dụng Direct scoring.")).toBeInTheDocument();
    vi.mocked(api.getAnchorBank).mockResolvedValue({ ...noBank, working: set });
    fireEvent.click(screen.getByRole("button", { name: "Tạo bộ anchor" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Thêm bài tham chiếu" })).toBeEnabled());
    expect(api.editAnchorBank).toHaveBeenCalledExactlyOnceWith();
    expect(screen.getByRole("heading", { name: "Chỉnh sửa bộ anchor" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Phiên bản")).not.toBeInTheDocument();
    expect(screen.queryByText(/ACTIVE|DRAFT|RETIRED/)).not.toBeInTheDocument();
  });

  it("shows one current bank and opens a copy-on-write editor with Sửa", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    vi.mocked(api.getAnchorBank).mockResolvedValueOnce({ ...noBank, current: active, current_count: 42 }).mockResolvedValue({ current: active, working: { ...set, id: task.id, version: 2 }, current_count: 42, working_count: 42 });
    vi.mocked(api.editAnchorBank).mockResolvedValue({ ...set, id: task.id, version: 2 });
    render(<AnchorWorkspace />);
    expect(await screen.findByText("42 bài tham chiếu")).toBeInTheDocument();
    expect(screen.getByText("Đang được AI sử dụng")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sửa" }));
    expect(await screen.findByText("Đang chỉnh sửa")).toBeInTheDocument();
    expect(screen.getByText(/Bộ đang dùng vẫn phục vụ chấm AI/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lưu & áp dụng" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Phiên bản")).not.toBeInTheDocument();
  });

  it("Thêm bài opens the working form without selecting or cloning a version", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    vi.mocked(api.getAnchorBank).mockResolvedValueOnce({ ...noBank, current: active, current_count: 1 }).mockResolvedValue({ current: active, working: set, current_count: 1, working_count: 1 });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Thêm bài" }));
    expect(await screen.findByRole("heading", { name: "Thêm bài tham chiếu" })).toBeInTheDocument();
    expect(api.editAnchorBank).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.getByLabelText("Bài viết của học viên")).toBeEnabled());
  });

  it("adds a Builder-backed response with four scores and unchanged paragraphs", async () => {
    vi.mocked(api.getAnchorBank).mockResolvedValue({ ...noBank, working: set });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Thêm bài tham chiếu" }));
    expect(screen.getByRole("button", { name: "Lưu & áp dụng" })).toBeDisabled();
    expect(screen.getByText("Lưu hoặc đóng biểu mẫu bài tham chiếu trước khi áp dụng bộ anchor.")).toBeInTheDocument();
    await screen.findByText(/Fictional Writing · v2/);
    fireEvent.change(screen.getByLabelText("Đề Writing đã xuất bản"), { target: { value: task.id } });
    fireEvent.change(screen.getByLabelText("Bài viết của học viên"), { target: { value: detail.response_text } });
    fireEvent.change(screen.getByLabelText("Task Achievement (TA)"), { target: { value: "6.5" } });
    expect(screen.queryByLabelText(/Feedback|Phản hồi/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(api.createAnchor).toHaveBeenCalledExactlyOnceWith(set.id, input));
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "Lưu & áp dụng" })).toBeEnabled());
  });

  it("edits and deletes a response only in the working revision, with explicit delete wording", async () => {
    vi.mocked(api.getAnchorBank).mockResolvedValue({ ...noBank, working: set, working_count: 1 });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 1 });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Sửa bài" }));
    expect(await screen.findByRole("heading", { name: "Chỉnh sửa bài tham chiếu" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ghi chú nội bộ"), { target: { value: "Đã kiểm tra" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(api.updateAnchor).toHaveBeenCalledExactlyOnceWith(detail.id, { ...input, admin_note: "Đã kiểm tra" }));
    await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
    fireEvent.click(await screen.findByRole("button", { name: "Xóa bài tham chiếu" }));
    const dialog = screen.getByRole("dialog", { name: "Xóa bài tham chiếu?" });
    expect(api.deleteAnchor).not.toHaveBeenCalled();
    vi.mocked(api.listAnchors).mockResolvedValue(emptyPage);
    fireEvent.click(within(dialog).getByRole("button", { name: "Xóa bài tham chiếu" }));
    await waitFor(() => expect(api.deleteAnchor).toHaveBeenCalledExactlyOnceWith(detail.id));
    expect(await screen.findByText("0 bài")).toBeInTheDocument();
  });

  it("applies changes and immediately removes write actions even if bank refresh fails", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    vi.mocked(api.getAnchorBank).mockResolvedValueOnce({ ...noBank, working: set, working_count: 1 }).mockRejectedValue(new Error("refresh failed"));
    vi.mocked(api.applyAnchorBank).mockResolvedValue(active);
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Lưu & áp dụng" }));
    await waitFor(() => expect(api.applyAnchorBank).toHaveBeenCalledExactlyOnceWith(set.id));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tải bộ anchor");
    expect(screen.getByText("Đang được AI sử dụng")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lưu & áp dụng" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xóa bài tham chiếu" })).not.toBeInTheDocument();
  });

  it("cancels unapplied changes and returns to the active bank", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    const working = { ...set, id: task.id, version: 2 };
    vi.mocked(api.getAnchorBank).mockResolvedValueOnce({ current: active, working, current_count: 1, working_count: 2 }).mockResolvedValue({ ...noBank, current: active, current_count: 1 });
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Hủy thay đổi" }));
    const dialog = screen.getByRole("dialog", { name: "Hủy các thay đổi chưa áp dụng?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Hủy thay đổi" }));
    await waitFor(() => expect(api.cancelAnchorBank).toHaveBeenCalledExactlyOnceWith(working.id));
    expect(await screen.findByText("Đang được AI sử dụng")).toBeInTheDocument();
    expect(api.deleteAnchorBank).not.toHaveBeenCalled();
  });

  it("requires bank deletion confirmation and explains future Direct fallback while retaining history", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    vi.mocked(api.getAnchorBank).mockResolvedValueOnce({ ...noBank, current: active, current_count: 1 }).mockResolvedValue(noBank);
    render(<AnchorWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Xóa bộ anchor" }));
    let dialog = screen.getByRole("dialog", { name: "Xóa bộ anchor đang dùng?" });
    expect(dialog).toHaveTextContent("Các lượt chấm trước đây và dữ liệu lịch sử không bị xóa.");
    expect(dialog).toHaveTextContent("tự chuyển sang Direct scoring");
    expect(api.deleteAnchorBank).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Hủy" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ anchor" }));
    dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Xóa bộ anchor" }));
    await waitFor(() => expect(api.deleteAnchorBank).toHaveBeenCalledExactlyOnceWith(active.id));
    expect(await screen.findByText("Chưa có bộ anchor đang dùng.")).toBeInTheDocument();
    expect(screen.getByText("CC, LR và GRA hiện sử dụng Direct scoring.")).toBeInTheDocument();
  });

  it("opens history on demand and keeps historical response content read-only", async () => {
    const active = { ...set, status: "ACTIVE" as const };
    const retired = { ...set, id: task.id, status: "RETIRED" as const };
    vi.mocked(api.getAnchorBank).mockResolvedValue({ ...noBank, current: active, current_count: 1 });
    vi.mocked(api.getAnchorHistory).mockResolvedValue({ items: [active, retired] });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 1 });
    render(<AnchorWorkspace />);
    await screen.findByText("Đang được AI sử dụng");
    const history = screen.getByRole("group", { name: "Lịch sử thay đổi" });
    expect(history).not.toHaveAttribute("open");
    expect(api.getAnchorHistory).not.toHaveBeenCalled();
    fireEvent.click(within(history).getByText("Lịch sử thay đổi", { selector: "summary" }));
    await within(history).findByText("Đã thay thế / ngừng dùng");
    fireEvent.click(within(history).getAllByRole("button", { name: "Xem" })[1]);
    expect(screen.getByText(/Đang xem lịch sử/)).toBeInTheDocument();
    const list = screen.getByRole("region", { name: "Các bài tham chiếu" });
    fireEvent.click(await within(list).findByRole("button", { name: "Xem" }));
    expect(await screen.findByRole("heading", { name: "Xem bài tham chiếu" })).toBeInTheDocument();
    expect(screen.getByLabelText("Bài viết của học viên")).toBeDisabled();
    expect(within(list).queryByRole("button", { name: "Sửa bài" })).not.toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "Xóa bài tham chiếu" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
    fireEvent.click(screen.getByRole("button", { name: "Quay lại bộ hiện tại" }));
    expect(screen.queryByText(/Đang xem lịch sử/)).not.toBeInTheDocument();
  });

  it("preserves filters, pagination and refresh without primary revision selection", async () => {
    vi.mocked(api.getAnchorBank).mockResolvedValue({ ...noBank, working: set });
    vi.mocked(api.listAnchors).mockResolvedValue({ ...emptyPage, items: [detail], total: 26 });
    render(<AnchorWorkspace />);
    expect(await screen.findByText("2026-10-07")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Kỹ năng"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Tìm bài tham chiếu"), { target: { value: "fictional" } });
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ set_id: set.id, task_number: 2, search: "fictional" })));
    fireEvent.click(screen.getByRole("button", { name: "Sau" }));
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })));
    fireEvent.click(screen.getByRole("button", { name: "Trước" }));
    await waitFor(() => expect(api.listAnchors).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 })));
    fireEvent.click(screen.getByRole("button", { name: "Làm mới" }));
    await waitFor(() => expect(api.getAnchorBank).toHaveBeenCalledTimes(2));
  });
});

describe("human anchor form validation", () => {
  it.each([1, 2] as const)("saves a standalone custom Task %s without a Builder reference", async number => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<AnchorForm detail={null} readOnly={false} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("radio", { name: "Nhập đề ngoài" }));
    expect(screen.queryByLabelText("Đề Writing đã xuất bản")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: String(number) } });
    const type = number === 1 ? "BAR_CHART" : "OPINION";
    fireEvent.change(screen.getByLabelText("Dạng bài"), { target: { value: type } });
    fireEvent.change(screen.getByLabelText("Đề bài / prompt"), { target: { value: "Fictional external prompt.\n\nDetails." } });
    fireEvent.change(screen.getByLabelText("Bài viết của học viên"), { target: { value: detail.response_text } });
    fireEvent.change(screen.getByLabelText(number === 1 ? "Task Achievement (TA)" : "Task Response (TR)"), { target: { value: "6.5" } });
    fireEvent.change(screen.getByLabelText("Nguồn / xuất xứ"), { target: { value: "Mẫu tự viết" } });
    fireEvent.change(screen.getByLabelText("Ghi chú nội bộ"), { target: { value: "Đã chấm thủ công" } });
    if (number === 1) expect(screen.getByText(/không phải mẫu benchmark TA có thể tái lập/)).toHaveTextContent("CC/LR/GRA vẫn có thể dùng cho TACS");
    else expect(screen.getByText(/Task 2 hiện vẫn dùng MTS/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledExactlyOnceWith({ source_kind: "CUSTOM_TASK", task_number: number, custom_prompt: "Fictional external prompt.\n\nDetails.", custom_task_type: type, response_text: detail.response_text, human_scores: detail.human_scores, provenance: "Mẫu tự viết", admin_note: "Đã chấm thủ công" }));
  });

  it("rejects a blank custom prompt and preserves the Builder picker when switching back", async () => {
    const onSave = vi.fn();
    render(<AnchorForm detail={detail} readOnly={false} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("radio", { name: "Nhập đề ngoài" }));
    fireEvent.change(screen.getByLabelText("Đề bài / prompt"), { target: { value: " \n " } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Vui lòng nhập đề bài cho đề ngoài.");
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: "Chọn đề có sẵn trong hệ thống" }));
    expect(screen.getByLabelText("Đề Writing đã xuất bản")).toHaveValue(task.id);
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledExactlyOnceWith(input));
  });

  it("loads custom metadata for editing and clears its task type when changing Task", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const custom: api.AnchorDetail = { ...detail, source_kind: "CUSTOM_TASK", custom_prompt: "External fictional chart.", task: { ...task, id: null, test_version_id: null, version_number: null, test_title: "Đề ngoài", task_type: "BAR_CHART" } };
    render(<AnchorForm detail={custom} readOnly={false} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Nhập đề ngoài" })).toBeChecked();
    expect(screen.getByLabelText("Đề bài / prompt")).toHaveValue(custom.custom_prompt);
    expect(screen.getByLabelText("Dạng bài")).toHaveValue("BAR_CHART");
    expect(api.listFrozenTasks).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "2" } });
    expect(screen.getByLabelText("Dạng bài")).toHaveValue("");
    expect(screen.queryByRole("option", { name: "Bar chart" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lưu bài tham chiếu" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ source_kind: "CUSTOM_TASK", task_number: 2, custom_prompt: custom.custom_prompt, custom_task_type: null, response_text: detail.response_text, human_scores: detail.human_scores, admin_note: null, provenance: null }));
  });

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
  it("previews the working bank without claiming it is already used by production", () => {
    render(<AnchorCoveragePanel editing coverage={{ ...coverage, evaluated_set: set, production_task1: [{ ...emptyRow("cc"), counts: { "6": 1, "7": 1 }, ladder: [6, 7], readiness: "PAIRWISE_USABLE" }] }} />);
    expect(screen.getByText(/Xem trước dữ liệu đang chỉnh sửa/)).toBeInTheDocument();
    expect(screen.getByText("Có thể dùng TACS sau khi áp dụng")).toBeInTheDocument();
    expect(screen.queryByText("Chưa có bộ anchor đang hoạt động.")).not.toBeInTheDocument();
    expect(screen.queryByText("Chấm bằng TACS")).not.toBeInTheDocument();
  });

  it("labels historical coverage as read-only even while a different bank is active", () => {
    render(<AnchorCoveragePanel historicalVersion={1} coverage={{ ...coverage, active_set: { ...set, status: "ACTIVE", version: 2 } }} />);
    expect(screen.getByText(/Dữ liệu lịch sử v1/)).toBeInTheDocument();
    expect(screen.getAllByText("Số liệu lịch sử · Chỉ đọc")).toHaveLength(3);
    expect(screen.queryByText("CC, LR và GRA hiện sẽ tự động dùng Direct scoring.")).not.toBeInTheDocument();
  });

  it("states the scoring architecture and Direct fallback before empty counts", () => {
    const onAdd = vi.fn();
    render(<AnchorCoveragePanel coverage={coverage} onAddAnchor={onAdd} />);
    expect(screen.getByText(/TA không dùng anchor/)).toHaveTextContent("luôn được chấm trực tiếp bằng Direct dựa trên biểu đồ/hình ảnh");
    expect(screen.getByText(/dùng TACS \(so sánh với bài tham chiếu\)/)).toHaveTextContent("khi đủ anchor; nếu chưa đủ, hệ thống tự dùng Direct");
    expect(screen.getByText(/hiện vẫn dùng MTS\. Anchor Task 2/)).toHaveTextContent("TR / CC / LR / GRA");
    const empty = screen.getByText("Chưa có bộ anchor đang hoạt động.");
    expect(screen.getByText("CC, LR và GRA hiện sẽ tự động dùng Direct scoring.")).toBeInTheDocument();
    expect(empty.compareDocumentPosition(screen.getByRole("article", { name: "Mức sẵn sàng CC" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Thêm bài tham chiếu" }));
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
    expect(within(research).getByRole("table", { name: "Task 1 · TA theo đề Writing" })).toHaveTextContent("Fictional Writing · v2 · Task 1 · TA");
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
