import { act, fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LibraryPage from "@/app/library/page";
import { getTests } from "@/lib/api/tests";
import { ContentSummary, publishedContentSummary } from "@/features/test-builder/content-summary";
import { accuracyLabel, focusedUnitLabel } from "@/features/exam/focused-attempt";
import { translate } from "@/lib/i18n/translations";
import type { VersionDetail } from "@/lib/api/schema";
import type { AttemptResponse } from "@/lib/api/attempts";
import { renderWithLocale } from "./locale-test-utils";
import { StartAttempt } from "@/features/exam/start-attempt";
import { StartFullMock } from "@/features/exam/start-full-mock";
import { startAttempt } from "@/lib/api/attempts";
import { startTestSession } from "@/lib/api/test-sessions";
import { ApiError } from "@/lib/api/client";
import { readFileSync } from "node:fs";
import { NewTestForm } from "@/features/test-builder/new-test-form";
import { createTest } from "@/lib/api/tests";
import { ListeningSectionEditor } from "@/features/test-builder/listening-section-editor";
import type { BuilderListeningPart } from "@/lib/api/builder";
import { WritingBuilder } from "@/features/test-builder/writing-builder";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";

vi.mock("@/lib/api/tests", () => ({ getTests: vi.fn(), getVersion: vi.fn(), createTest: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/lib/api/attempts", () => ({ startAttempt: vi.fn() }));
vi.mock("@/lib/api/test-sessions", () => ({ startTestSession: vi.fn() }));
describe("workspace localization boundaries", () => {
  it("keeps Writing Builder prompt values while translating top-level task fields and save actions", () => {
    const version = { id: "version", test_id: "test", test_title: "Section 2", version_number: 1, status: "DRAFT", modules: [{ id: "module", revision: 1, module_type: "WRITING", title: "Writing", recommended_duration_seconds: 3600, audio_asset: null, passages: [], listening_parts: [], writing_tasks: [{ id: "task", revision: 1, task_number: 1, task_type: null, prompt: "Describe <raw> data.", image_asset_id: null, image_asset: null, minimum_recommended_words: 150, recommended_duration_seconds: 1200, order_index: 0 }] }] } satisfies Parameters<typeof WritingBuilder>[0]["version"];
    const before = JSON.stringify(version);
    renderWithLocale(<BuilderLifecycleProvider><WritingBuilder version={version} /></BuilderLifecycleProvider>);
    const prompt = screen.getByLabelText("Prompt");
    fireEvent.change(prompt, { target: { value: "Authored draft <raw>" } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByLabelText("Đề bài")).toBe(prompt);
    expect(prompt).toHaveValue("Authored draft <raw>");
    expect(screen.getByRole("button", { name: "Lưu bài viết 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("Số từ tối thiểu đề xuất")).toHaveValue(150);
    expect(JSON.stringify(version)).toBe(before);
  });
  it("translates new-test metadata chrome without changing the authored draft or payload", async () => {
    vi.mocked(createTest).mockResolvedValue({ id: "new-test" } as Awaited<ReturnType<typeof createTest>>);
    renderWithLocale(<NewTestForm />);
    const title = screen.getByRole("textbox", { name: "Test title" });
    const description = screen.getByRole("textbox", { name: /Description/ });
    fireEvent.change(title, { target: { value: "Section 2 <raw>" } });
    fireEvent.change(description, { target: { value: "Mô tả authored" } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("textbox", { name: "Tiêu đề đề" })).toBe(title);
    expect(title).toHaveValue("Section 2 <raw>");
    expect(description).toHaveValue("Mô tả authored");
    expect(createTest).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Tạo bản nháp" })); });
    expect(createTest).toHaveBeenCalledExactlyOnceWith({ title: "Section 2 <raw>", description: "Mô tả authored" });
  });
  it("translates section chrome while specialized range help and persisted fallback stay exact", () => {
    const part = { id: "section", revision: 1, title: "Section 2", order_index: 1, question_groups: [], audio_start_seconds: null, audio_end_seconds: null } satisfies BuilderListeningPart;
    const before = JSON.stringify(part);
    renderWithLocale(<ListeningSectionEditor part={part} duration={null} currentPosition={() => 0} onPreview={vi.fn()} onPersisted={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "Section title / internal label" });
    const help = screen.getByText(/Optional for full Listening/).textContent;
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("textbox", { name: "Tiêu đề phần / nhãn nội bộ" })).toBe(input);
    expect(input).toHaveValue("Section 2");
    expect(screen.getByText(/Optional for full Listening/).textContent).toBe(help);
    expect(screen.getByRole("button", { name: "Preview section clip" })).toBeInTheDocument();
    expect(JSON.stringify(part)).toBe(before);
    const source = readFileSync("src/features/test-builder/listening-section-editor.tsx", "utf8");
    expect(source).toContain('title: part.title ?? `Section ${part.order_index + 1}`');
  });
  beforeEach(() => { window.localStorage.clear(); vi.clearAllMocks(); });
  it("translates Library empty state without refetching server data", async () => {
    vi.mocked(getTests).mockResolvedValue([]);
    renderWithLocale(await LibraryPage());
    expect(screen.getByRole("heading", { name: "Choose your next test" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { name: "Chọn đề tiếp theo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Chưa có đề đã xuất bản" })).toBeInTheDocument();
    expect(getTests).toHaveBeenCalledOnce();
  });
  it("generated labels translate while authored titles and prompt excerpts stay exact", () => {
    const fixtureModule = { module_type: "LISTENING", listening_sections: [{ order_index: 1, title: "Section 2", question_groups: [{ question_type: "short_answer" }] }] } as VersionDetail["modules"][number];
    const units = [...publishedContentSummary(fixtureModule), { heading: { message: "common.taskNumber", params: { number: 1 } }, title: null, taskType: "PIE_CHART", excerpt: "Đề thử <img> / option A" }] as Parameters<typeof ContentSummary>[0]["units"];
    expect(units[0].heading).toEqual({ message: "common.sectionNumber", params: { number: 2 } });
    const before = JSON.stringify({ fixtureModule, units });
    renderWithLocale(<ContentSummary units={units} />);
    const authored = screen.getByText("Section 2", { selector: ".font-semibold" });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByText("Phần 2")).toBeInTheDocument();
    expect(screen.getByText("Section 2")).toBe(authored);
    expect(screen.getByText("Đề thử <img> / option A")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(JSON.stringify({ fixtureModule, units })).toBe(before);
  });
  it("uses focused metadata instead of parsing authored titles or server labels", () => {
    const attempt = { scope: "FOCUSED_UNIT", focused_unit: { kind: "LISTENING_PART", order_index: 1, label: "server label", title: "Section 2" } } as Pick<AttemptResponse, "scope" | "focused_unit">;
    expect(focusedUnitLabel(attempt)).toBe("Section 2 · Section 2");
    expect(focusedUnitLabel(attempt, (key, params) => translate("vi", key, params))).toBe("Phần 2 · Section 2");
    expect(accuracyLabel(2, 3, (key, params) => translate("vi", key, params))).toBe("66.7% chính xác");
    expect(accuracyLabel(null, 3)).toBeNull();
    expect(accuracyLabel(2, 0)).toBeNull();
  });
  it.each([false, true])("localizes standalone start errors while preserving timer/request values (raw diagnostic %s)", async (raw) => {
    vi.mocked(startAttempt).mockRejectedValue(raw ? new ApiError("UNKNOWN", "Diagnostic <raw>", 400) : {});
    renderWithLocale(<StartAttempt versionId="version" module="READING" />);
    const timer = screen.getByRole("combobox");
    fireEvent.change(timer, { target: { value: "3000" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start Reading" })); });
    expect(screen.getByRole("alert")).toHaveTextContent(raw ? "Diagnostic <raw>" : "Could not start attempt.");
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("combobox")).toBe(timer); expect(timer).toHaveValue("3000");
    expect(screen.getByRole("alert")).toHaveTextContent(raw ? "Diagnostic <raw>" : "Không thể bắt đầu bài làm.");
    expect(startAttempt).toHaveBeenCalledExactlyOnceWith({ test_version_id: "version", module: "READING", timer: { mode: "COUNTDOWN", duration_seconds: 3000 } });
  });
  it("keeps Full Mock start pending without repeating the request on locale change", async () => {
    let finish!: (result: Awaited<ReturnType<typeof startTestSession>>) => void;
    vi.mocked(startTestSession).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderWithLocale(<StartFullMock versionId="version" />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start Full Mock" })); });
    const pending = screen.getByRole("button", { name: "Starting…" });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("button", { name: "Đang bắt đầu…" })).toBe(pending); expect(pending).toBeDisabled();
    expect(startTestSession).toHaveBeenCalledExactlyOnceWith("version");
    await act(async () => { finish({ current_attempt: { attempt_id: "attempt" } } as Awaited<ReturnType<typeof startTestSession>>); });
  });
  it("keeps server fetchers outside client presentation and exports a client summary view separately", () => {
    for (const path of ["src/components/home/overview-content.tsx", "src/features/practice/library-content.tsx", "src/features/test-builder/content-summary-view.tsx"]) {
      const source = readFileSync(path, "utf8"); expect(source).toMatch(/^"use client";/); expect(source).not.toContain("server-client");
      expect(source).not.toMatch(/import\s+\{[^}]*\b(getTests|getVersion|getAdminStats|getProfile)\b/);
    }
    for (const path of ["src/app/page.tsx", "src/app/library/page.tsx", "src/app/library/[versionId]/page.tsx"]) {
      const source = readFileSync(path, "utf8"); expect(source).not.toContain('"use client"'); expect(source).toContain("serverApiRequest");
    }
    expect(readFileSync("src/features/test-builder/content-summary.tsx", "utf8")).not.toContain('"use client"');
  });
});
