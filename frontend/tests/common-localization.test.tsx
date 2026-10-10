import { fireEvent, screen, within, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import { PageHeading } from "@/components/ui/page-heading";
import { EmptyState } from "@/components/ui/empty-state";
import { ModuleBadge } from "@/components/ui/module-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { AuthProvider } from "@/features/auth/auth-provider";
import { getCurrentUser, logout } from "@/lib/api/auth";
import { UiText } from "@/lib/i18n/locale-provider";
import { renderWithLocale } from "./locale-test-utils";

const navigation = vi.hoisted(() => ({ pathname: "/", push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname, useRouter: () => navigation }));
vi.mock("@/lib/api/auth", () => ({ getCurrentUser: vi.fn(), logout: vi.fn() }));
vi.mock("next/link", () => ({ default: ({ prefetch, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean }) => <a {...props} data-prefetch={prefetch === false ? "disabled" : "automatic"} /> }));

describe("common localization", () => {
  beforeEach(() => {
    vi.resetAllMocks(); window.localStorage.clear(); navigation.pathname = "/";
    document.documentElement.dataset.theme = "light";
    vi.mocked(getCurrentUser).mockResolvedValue({ id: "user", display_name: "Nguyễn <Learner>", role: "USER" } as Awaited<ReturnType<typeof getCurrentUser>>);
  });
  it("common primitives accept translated nodes and raw authored titles", () => {
    expect(renderToString(<PageHeading title="Section 2" description={<UiText message="common.back" />} />)).toContain("Section 2");
    renderWithLocale(<><PageHeading title="Section 2" eyebrow={<UiText message="common.review" />} /><EmptyState title={<UiText message="common.review" />} description="Bản thảo <img>" /><ModuleBadge module="LISTENING" label={<UiText message="common.listening" />} /><StatusBadge status="PAUSED" label={<UiText message="common.paused" />} /><StatusBadge status="UNKNOWN_CODE" label="Raw value" /></>);
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { name: "Section 2" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Xem lại" })).toBeInTheDocument();
    expect(screen.getByText("Bản thảo <img>")).toBeInTheDocument();
    expect(screen.getByText("Nghe")).toHaveClass("module-listening");
    expect(screen.getByText("Đã tạm dừng")).toHaveClass("status-paused");
    expect(screen.getByText("Raw value")).toHaveClass("status-archived");
  });
  it("open logout dialog changes language without recreation or auth recheck", async () => {
    let finish!: () => void;
    vi.mocked(logout).mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    renderWithLocale(<AuthProvider><AppShell currentYear={2026}>Content</AppShell></AuthProvider>);
    await screen.findByText("Nguyễn <Learner>");
    fireEvent.click(screen.getByRole("button", { name: "Logout" }));
    const dialog = screen.getByRole("dialog");
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(cancel).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByRole("dialog", { name: "Đăng xuất?" })).toBe(dialog);
    expect(within(dialog).getByText("Bạn có chắc muốn đăng xuất khỏi tài khoản?" )).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Hủy" })).toBe(cancel);
    expect(cancel).toHaveFocus();
    expect(screen.getByText("Người dùng")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tổng quan IELTS Studio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bỏ qua điều hướng" })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByText("Luyện tập và biên soạn đề")).toBeInTheDocument();
    expect(screen.getByText("Nguyễn <Learner>")).toBeInTheDocument();
    expect(getCurrentUser).toHaveBeenCalledOnce();
    expect(navigation.refresh).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Đăng xuất" }));
    expect(within(dialog).getByRole("button", { name: "Đang xử lý…" })).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(logout).toHaveBeenCalledOnce();
    finish(); await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
  it.each(["server diagnostic <unchanged>", null])("keeps raw session diagnostics and translates only owned fallbacks (%s)", async (message) => {
    vi.mocked(getCurrentUser).mockRejectedValue(message ? new Error(message) : { offline: true });
    renderWithLocale(<AuthProvider><AppShell currentYear={2026}>Content</AppShell></AuthProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent(message ?? "The session could not be checked.");
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("alert")).toHaveTextContent(message ?? "Không thể kiểm tra phiên đăng nhập.");
    expect(getCurrentUser).toHaveBeenCalledOnce();
  });
  it("honors explicit dialog labels and keeps preference storage independent", () => {
    renderWithLocale(<><AppShell currentYear={2026}>Content</AppShell><ConfirmDialog open title="Authored" description="Raw" confirmLabel="Confirm" cancelLabel="Keep" pendingLabel="Wait" pending onCancel={vi.fn()} onConfirm={vi.fn()} /></>);
    const write = vi.spyOn(Storage.prototype, "setItem");
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(write.mock.calls.every(([key]) => key === "ielts-locale")).toBe(true);
    expect(screen.getByRole("button", { name: "Keep" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Wait" })).toBeDisabled();
    write.mockClear(); fireEvent.click(screen.getByRole("button", { name: "Dùng giao diện tối" }));
    expect(write).toHaveBeenCalledExactlyOnceWith("ielts-theme", "dark");
    write.mockRestore();
  });
  it("does not add a global skip link to attempts", () => {
    navigation.pathname = "/attempt/id/paused";
    renderWithLocale(<AppShell currentYear={2026}>Questions</AppShell>);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByRole("main")).toHaveClass("exam-shell");
  });
});
