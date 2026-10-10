import { act, fireEvent, render, screen, within, type RenderResult } from "@testing-library/react";
import { useEffect, type ReactElement } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import { themeInitializationScript } from "@/app/layout";
import { LocaleProvider, useLocale } from "@/lib/i18n/locale-provider";
import { AuthProvider } from "@/features/auth/auth-provider";
import { AuthForm } from "@/features/auth/auth-form";
import { SkillPractice } from "@/features/practice/skill-practice";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { WritingRunner } from "@/features/writing/writing-runner";
import { TestSessionTransition } from "@/features/exam/test-session-transition";
import VersionEditorPage from "@/app/admin/tests/[testId]/versions/[versionId]/edit/page";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import { TransferPortal } from "@/features/transfer/transfer-portal";
import * as authApi from "@/lib/api/auth";
import * as attempts from "@/lib/api/attempts";
import * as examApi from "@/lib/api/exam";
import { getBuilderVersion } from "@/lib/api/builder";
import { advanceTestSession, type TestSession } from "@/lib/api/test-sessions";
import { importTests, exportTests } from "@/lib/api/transfer";
import { updateTest } from "@/lib/api/tests";
import { ApiError } from "@/lib/api/client";
import type { VersionDetail } from "@/lib/api/schema";
import type { BuilderVersion } from "@/lib/api/builder";

const route = vi.hoisted(() => ({ pathname: "/", push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname, useRouter: () => route, useSearchParams: () => new URLSearchParams(), notFound: vi.fn(), redirect: vi.fn() }));
vi.mock("@/lib/api/auth", async (original) => ({ ...await original<typeof authApi>(), getCurrentUser: vi.fn(), logout: vi.fn(), login: vi.fn(), register: vi.fn() }));
vi.mock("@/lib/api/attempts", async (original) => ({ ...await original<typeof attempts>(), startAttempt: vi.fn(), getAttempt: vi.fn(), recordActivity: vi.fn(), recordNavigation: vi.fn(), saveAnswer: vi.fn(), saveWritingResponse: vi.fn(), pauseAttempt: vi.fn(), resumeAttempt: vi.fn() }));
vi.mock("@/lib/api/exam", async (original) => ({ ...await original<typeof examApi>(), getExam: vi.fn(), submitAttempt: vi.fn(), saveFlag: vi.fn(), createHighlight: vi.fn(), deleteHighlight: vi.fn() }));
vi.mock("@/lib/api/builder", async (original) => ({ ...await original<typeof import("@/lib/api/builder")>(), getBuilderVersion: vi.fn() }));
vi.mock("@/lib/api/tests", async (original) => ({ ...await original<typeof import("@/lib/api/tests")>(), updateTest: vi.fn() }));
vi.mock("@/lib/api/transfer", () => ({ importTests: vi.fn(), exportTests: vi.fn() }));
vi.mock("@/lib/api/test-sessions", async (original) => ({ ...await original<typeof import("@/lib/api/test-sessions")>(), advanceTestSession: vi.fn() }));

const id = (n: number) => `22222222-2222-4222-8222-${String(n).padStart(12, "0")}`;
const time = "2026-10-11T00:00:00.000Z";
const user: authApi.AuthUser = { id: id(1), email: "raw@example.com", display_name: "Nguyễn Raw User", role: "USER", is_active: true, created_at: time, updated_at: time, last_login_at: null };
function exam(module: "READING" | "LISTENING" | "WRITING", focused: boolean): examApi.ExamPayload {
  const group = { id: id(20), question_type: "short_answer", instruction: "Authored IELTS instruction", config: {}, order_index: 0, questions: [{ id: id(21), number: 2, prompt: "Fictional authored question", config: { max_words: 3 }, order_index: 0, value: "original", flagged: true, answer_revision: 2 }] };
  const attempt: attempts.AttemptResponse = { attempt_id: id(2), test_version_id: id(3), module, scope: focused ? "FOCUSED_UNIT" : "FULL_MODULE", attempt_context: "STANDALONE", focused_unit: focused ? { kind: module === "READING" ? "READING_PASSAGE" : module === "LISTENING" ? "LISTENING_PART" : "WRITING_TASK", id: id(10), order_index: 1, label: "Section 2", title: "Section 2" } : null,
    status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: time, paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: time, finished_at: null, elapsed_seconds: 100, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: time };
  return { attempt, test_title: "Fictional authored test", passages: module === "READING" ? [{ id: id(10), title: "Section 2", order_index: 1, blocks: [{ id: id(11), type: "paragraph", label: "A", text: "Fictional passage remains exact." }], question_groups: [group] }] : [],
    listening_parts: module === "LISTENING" ? [{ id: id(10), title: "Section 2", order_index: 1, audio_start_seconds: 10, audio_end_seconds: 40, question_groups: [group] }] : [], listening_audio_asset: module === "LISTENING" ? { id: id(12), original_name: "raw.mp3", mime_type: "audio/mpeg", file_size: 100, content_url: "/assets/raw" } : null,
    writing_tasks: module === "WRITING" ? [{ id: id(10), task_number: 2, order_index: 1, prompt: "Fictional Writing prompt remains exact.", image_asset_id: null, image_asset: null, minimum_recommended_words: 250, recommended_duration_seconds: 2400, content: "Learner response remains exact", word_count: 4, response_revision: 2 }] : [], highlights: [] };
}
const draft: BuilderVersion = { id: id(3), test_id: id(4), test_title: "Fictional authored test", test_description: "Raw description", version_number: 1, status: "DRAFT", modules: [{ id: id(5), revision: 1, module_type: "READING", title: "Raw module title", recommended_duration_seconds: 3600, audio_asset: null, listening_parts: [], writing_tasks: [],
  passages: exam("READING", false).passages.map((passage) => ({ ...passage, revision: 1, question_groups: passage.question_groups.map((group) => ({ ...group, question_type: "short_answer", revision: 1, questions: group.questions.map((question) => ({ ...question, answer_key: { kind: "TEXT", accepted: ["Raw key"] }, explanation: "Raw explanation" })) })) })) }] };
const practiceVersion: VersionDetail = { id: id(3), test_id: id(4), test_title: draft.test_title, version_number: 1, status: "PUBLISHED", created_at: time, published_at: time, modules: ["READING", "LISTENING"].map((module_type, index) => ({ id: id(5 + index), module_type: module_type as "READING" | "LISTENING", title: null, recommended_duration_seconds: 1800, passage_count: module_type === "READING" ? 1 : 0, listening_part_count: module_type === "LISTENING" ? 1 : 0, writing_task_count: 0, question_count: 1, has_audio: false,
  reading_passages: module_type === "READING" ? [{ id: id(10), title: "Section 2", order_index: 1, question_groups: [{ question_type: "short_answer", start_number: 2, end_number: 2, question_count: 1 }] }] : [], listening_sections: module_type === "LISTENING" ? [{ id: id(10), title: "Section 2", order_index: 1, question_groups: [{ question_type: "short_answer", start_number: 2, end_number: 2, question_count: 1 }] }] : [] })) };
let changeLocale: (locale: "en" | "vi") => void;
function LocaleDriver() { const { setLocale } = useLocale(); useEffect(() => { changeLocale = setLocale; }, [setLocale]); return null; }
async function composition(feature: ReactElement) {
  let view!: RenderResult;
  await act(async () => { view = render(<LocaleProvider><AuthProvider><AppShell currentYear={2026}>{feature}</AppShell></AuthProvider><LocaleDriver /></LocaleProvider>); });
  return view;
}
const requests = () => [authApi.getCurrentUser, authApi.login, authApi.register, attempts.startAttempt, attempts.saveAnswer, attempts.saveWritingResponse, attempts.recordActivity, attempts.recordNavigation, attempts.getAttempt, examApi.getExam, examApi.submitAttempt, advanceTestSession, importTests, exportTests, updateTest, route.push, route.refresh, route.replace].map((spy) => structuredClone(vi.mocked(spy).mock.calls));
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date(time)); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear(); document.documentElement.dataset.theme = "light"; route.pathname = "/";
  vi.mocked(authApi.getCurrentUser).mockResolvedValue(user); vi.mocked(getBuilderVersion).mockResolvedValue(draft);
  vi.mocked(attempts.recordActivity).mockResolvedValue({} as never); vi.mocked(attempts.recordNavigation).mockResolvedValue(undefined);
  Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: vi.fn() });
  for (const name of ["play", "pause", "load"] as const) Object.defineProperty(HTMLMediaElement.prototype, name, { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

const rows = [
  { role: "guest", locale: "en", theme: "light", feature: "auth", path: "/login" },
  { role: "USER", locale: "vi", theme: "dark", feature: "practice", path: "/practice" },
  { role: "USER", locale: "en", theme: "dark", feature: "history", path: "/history" },
  { role: "USER", locale: "en", theme: "light", feature: "review", path: "/review/attempt" },
  { role: "ADMIN", locale: "vi", theme: "light", feature: "builder", path: `/admin/tests/${id(4)}/versions/${id(3)}/edit` },
  { role: "ADMIN", locale: "vi", theme: "light", feature: "transfer", path: "/transfer" },
  { role: "ADMIN", locale: "vi", theme: "dark", feature: "preview", path: `/admin/tests/${id(4)}/versions/${id(3)}/preview` },
] as const;
it.each(rows)("role locale theme route matrix preserves chrome and feature identity: $role $locale $theme $feature", async (row) => {
  route.pathname = row.path; localStorage.setItem("ielts-locale", row.locale); localStorage.setItem("ielts-theme", row.theme); window.eval(themeInitializationScript);
  if (row.role === "guest") vi.mocked(authApi.getCurrentUser).mockRejectedValue(new ApiError("AUTHENTICATION_REQUIRED", "raw server diagnostic", 401));
  else vi.mocked(authApi.getCurrentUser).mockResolvedValue({ ...user, role: row.role });
  const reading = exam("READING", true);
  const review: Awaited<ReturnType<typeof examApi.getReadingReview>> = { review: { attempt: { ...reading.attempt, status: "SUBMITTED", raw_score: 1, max_score: 1 }, test_title: reading.test_title, answers: [] }, passages: draft.modules[0].passages, highlights: [] };
  const feature = row.feature === "auth" ? <AuthForm mode="login" /> : row.feature === "practice" ? <SkillPractice versions={[practiceVersion]} /> : row.feature === "history" ? <AttemptHistoryList initialHistory={{ items: [], groups: [], sessions: [], total: 0 }} /> : row.feature === "review" ? <ReadingReviewView data={review} /> : row.feature === "builder" ? await VersionEditorPage({ params: Promise.resolve({ testId: id(4), versionId: id(3) }), searchParams: Promise.resolve({ workspace: "reading" }) }) : row.feature === "transfer" ? <TransferPortal tests={[{ id: id(4), title: "Raw transfer test", latestVersion: 1, states: ["DRAFT"], skills: ["READING"], archived: false }]} /> : <DraftPreview version={draft} moduleType="READING" />;
  const view = await composition(feature);
  const nav = view.container.querySelector(".primary-nav")!;
  expect(within(nav as HTMLElement).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/", "/library", "/practice", "/history", "/analytics", "/admin", "/admin/tests", "/transfer"].slice(0, row.role === "guest" ? 1 : row.role === "USER" ? 5 : 8));
  expect(view.container.querySelectorAll(".primary-nav")).toHaveLength(1); expect(view.container.querySelector(".app-header")).toBeInTheDocument();
  expect(document.documentElement.lang).toBe(row.locale); expect(document.documentElement.dataset.theme).toBe(row.theme);
  if (row.feature === "preview") { expect(view.container.querySelector(".app-footer")).toBeNull(); expect(view.container.querySelector(".exam-footer")).toBeInTheDocument(); }
  else expect(view.container.querySelector(".app-footer")).toHaveTextContent("© 2026 IELTS Studio");
  let node: Element | null = null;
  if (row.feature === "auth") { node = screen.getByLabelText("Email"); fireEvent.change(node, { target: { value: "raw@email.test" } }); }
  if (row.feature === "practice") { fireEvent.click(screen.getByRole("button", { name: "Nghe" })); node = screen.getByRole("searchbox"); fireEvent.change(node, { target: { value: "Section 2" } }); }
  if (row.feature === "history") { fireEvent.click(screen.getByRole("tab", { name: "Focused practice" })); node = screen.getByRole("tab", { selected: true }); }
  if (row.feature === "builder") node = view.container.querySelector('.builder-local-nav [aria-current="page"]');
  if (row.feature === "transfer") { node = screen.getByLabelText("Gói đề ZIP"); fireEvent.change(node, { target: { files: [new File(["zip"], "raw.zip")] } }); }
  if (row.feature === "preview") { node = screen.getByLabelText("Câu hỏi 2"); fireEvent.change(node, { target: { value: "Preview answer" } }); }
  const before = requests(); const featureHtml = view.container.querySelector("main.app-content");
  act(() => changeLocale(row.locale === "en" ? "vi" : "en"));
  expect(requests()).toEqual(before); expect(authApi.getCurrentUser).toHaveBeenCalledTimes(1); expect(view.container.querySelector("main.app-content")).toBe(featureHtml); expect(document.documentElement.dataset.theme).toBe(row.theme); expect(view.container.contains(node)).toBe(node !== null);
  if (row.feature === "auth") expect(node).toHaveValue("raw@email.test");
  if (row.feature === "practice") { expect(node).toHaveValue("Section 2"); expect(screen.getByRole("button", { name: "Listening" })).toHaveAttribute("aria-pressed", "true"); }
  if (row.feature === "history") expect(node).toHaveAttribute("aria-selected", "true");
  if (row.feature === "builder") expect(node).toHaveAttribute("aria-current", "page");
  if (row.feature === "transfer") expect((node as HTMLInputElement).files?.[0].name).toBe("raw.zip");
  if (row.feature === "preview") expect(node).toHaveValue("Preview answer");
});

it.each((["READING", "LISTENING", "WRITING"] as const).flatMap((module) => [false, true].map((focused) => ({ module, focused }))))("attempt chrome and identity survive locale switch: $module focused=$focused", async ({ module, focused }) => {
  route.pathname = `/attempt/${id(2)}`; const data = exam(module, focused); const raw = JSON.stringify(data);
  const Runner = module === "READING" ? ReadingRunner : module === "LISTENING" ? ListeningRunner : WritingRunner;
  const view = await composition(<Runner initial={data} />); await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  const runner = view.container.querySelector(".exam-runner"); const input = screen.getByRole("textbox"); fireEvent.change(input, { target: { value: "Exact unsaved response" } });
  const audio = view.container.querySelector("audio"); if (audio) { Object.defineProperty(audio, "duration", { configurable: true, value: 100 }); fireEvent.loadedMetadata(audio); audio.currentTime = 25; audio.playbackRate = 1.25; }
  const before = requests(); act(() => changeLocale("vi"));
  expect(screen.getByRole("button", { name: "Tạm dừng và thoát" })).toBeInTheDocument(); expect(view.container.querySelector(".exam-runner")).toBe(runner); expect(screen.getByRole("textbox")).toBe(input); expect(input).toHaveValue("Exact unsaved response"); expect(requests()).toEqual(before); expect(JSON.stringify(data)).toBe(raw);
  expect(view.container.querySelector(".app-header, .app-footer, .app-content, .app-shell")).toBeNull(); expect(view.container.querySelector(".exam-shell")).toBeInTheDocument();
  if (audio) { expect(view.container.querySelector("audio")).toBe(audio); expect([audio.currentTime, audio.playbackRate]).toEqual([25, 1.25]); }
});

it("keeps Full Mock transition chrome and advance identity while locale changes", async () => {
  route.pathname = "/test-session/session";
  const initial: TestSession = { session_id: id(9), test_version_id: id(3), test_title: "Raw mock", version_number: 1, status: "IN_PROGRESS", started_at: time, finished_at: null, current_module: "WRITING", next_module: "WRITING", current_attempt: null, attempts: [{ attempt_id: id(2), module: "READING", status: "SUBMITTED", raw_score: 32, max_score: 40, band_score: 7, elapsed_seconds: 3600 }], warnings: ["Raw warning"], overall_band_score: null };
  const view = await composition(<TestSessionTransition initial={initial} />); const button = screen.getByRole("button", { name: "Continue to Writing" }); const before = requests();
  act(() => changeLocale("vi")); expect(screen.getByRole("button", { name: "Tiếp tục đến Viết" })).toBe(button); expect(screen.getByText("Raw warning")).toBeInTheDocument(); expect(requests()).toEqual(before); expect(view.container.querySelector(".app-footer")).toBeInTheDocument();
});

it("keeps logout dialog node, focus and one-request guard across locale and theme changes", async () => {
  let finish!: () => void; vi.mocked(authApi.logout).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  await composition(<p>Workspace</p>); fireEvent.click(screen.getByRole("button", { name: "Logout" }));
  const dialog = screen.getByRole("dialog"); const focus = document.activeElement;
  act(() => changeLocale("vi")); expect(screen.getByRole("dialog")).toBe(dialog); expect(document.activeElement).toBe(focus);
  fireEvent.click(screen.getByRole("button", { name: "Dùng giao diện tối" })); expect(document.documentElement.lang).toBe("vi"); expect(document.documentElement.dataset.theme).toBe("dark");
  const confirm = within(dialog).getByRole("button", { name: "Đăng xuất" }); fireEvent.click(confirm); fireEvent.click(confirm);
  expect(authApi.logout).toHaveBeenCalledTimes(1); expect(authApi.getCurrentUser).toHaveBeenCalledTimes(1); act(() => changeLocale("en")); expect(screen.getByRole("dialog")).toBe(dialog);
  await act(async () => finish()); expect(route.push).toHaveBeenCalledExactlyOnceWith("/login");
});

it.each(["invalid", "throwing"])("independent preferences remain usable after %s storage", async (mode) => {
  localStorage.setItem("ielts-locale", "unknown"); localStorage.setItem("ielts-theme", "system");
  if (mode === "throwing") { vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked read"); }); vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked write"); }); }
  window.eval(themeInitializationScript); await composition(<input aria-label="Draft" defaultValue="kept" />); const input = screen.getByLabelText("Draft");
  expect(document.documentElement.lang).toBe("en"); expect(document.documentElement.dataset.theme).toBe("light"); act(() => changeLocale("vi")); fireEvent.click(screen.getByRole("button", { name: "Dùng giao diện tối" }));
  expect(document.documentElement.lang).toBe("vi"); expect(document.documentElement.dataset.theme).toBe("dark"); expect(screen.getByLabelText("Draft")).toBe(input); expect(input).toHaveValue("kept"); expect(screen.queryByRole("alert")).not.toBeInTheDocument(); expect(authApi.getCurrentUser).toHaveBeenCalledTimes(1); expect(route.refresh).not.toHaveBeenCalled();
});
