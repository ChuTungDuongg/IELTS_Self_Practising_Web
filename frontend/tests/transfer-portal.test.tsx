import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import { AuthProvider } from "@/features/auth/auth-provider";
import TransferPage from "@/app/transfer/page";
import { TransferPortal } from "@/features/transfer/transfer-portal";
import { exportTests, importTests } from "@/lib/api/transfer";
import { getTests } from "@/lib/api/tests";
import { getCurrentUser } from "@/lib/api/auth";
import { renderWithLocale } from "./locale-test-utils";

vi.mock("next/navigation", () => ({
  usePathname: () => "/transfer",
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("@/lib/api/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/auth")>();
  return { ...actual, getCurrentUser: vi.fn() };
});
vi.mock("@/lib/api/transfer", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/transfer")>();
  return { ...actual, exportTests: vi.fn(), importTests: vi.fn() };
});
vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, getTests: vi.fn(), getVersion: vi.fn() };
});

const testId = "11111111-1111-4111-8111-111111111111";
const options = [{ id: testId, title: "Fictional portable test", latestVersion: 2, states: ["PUBLISHED", "DRAFT"], skills: ["READING", "LISTENING", "WRITING"], archived: false }];

describe("Test transfer portal", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(getCurrentUser).mockResolvedValue({
      id: testId,
      email: "admin@example.com",
      display_name: "E2E Administrator",
      role: "ADMIN",
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_login_at: null,
    });
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:test"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("retains the selected File and test IDs across locale switches and pending import", async () => {
    let finish!: (result: Awaited<ReturnType<typeof importTests>>) => void;
    vi.mocked(importTests).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderWithLocale(<TransferPortal tests={options} />);
    const selected = screen.getByLabelText("Select Fictional portable test");
    fireEvent.click(selected);
    const picker = screen.getByLabelText("Test package ZIP");
    const file = new File(["zip"], "Đề <raw>.zip", { type: "application/zip" });
    fireEvent.change(picker, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByLabelText("Gói đề ZIP")).toBe(picker);
    expect((picker as HTMLInputElement).files?.[0]).toBe(file);
    expect(selected).toBeChecked();
    expect(screen.getByText("Đã chọn: Đề <raw>.zip")).toBeInTheDocument();
    expect(importTests).not.toHaveBeenCalled();
    expect(exportTests).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Nhập" }));
    fireEvent.click(screen.getByText("Switch to English"));
    expect(screen.getByRole("button", { name: "Importing…" })).toBeDisabled();
    expect(importTests).toHaveBeenCalledExactlyOnceWith(file);
    finish({ imported_tests: [], version_count: 0, asset_count: 0 });
    await screen.findByText("Imported 0 tests");
    vi.mocked(exportTests).mockResolvedValue({ blob: new Blob(["zip"]), filename: "raw.zip" });
    fireEvent.click(screen.getByRole("button", { name: "Export selected" }));
    await waitFor(() => expect(exportTests).toHaveBeenCalledExactlyOnceWith([testId]));
  });

  it("adds Transfer to authenticated ADMIN navigation", async () => {
    render(<AuthProvider><AppShell currentYear={2026}><p>content</p></AppShell></AuthProvider>);
    expect(await screen.findByRole("link", { name: "Transfer" })).toHaveAttribute("href", "/transfer");
  });

  it("renders the /transfer page", async () => {
    vi.mocked(getTests).mockResolvedValue([]);
    render(await TransferPage());
    expect(screen.getByRole("heading", { name: "Test transfer" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Export authored tests" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Import test package" })).toBeInTheDocument();
  });

  it("selects tests and calls the binary export endpoint", async () => {
    vi.mocked(exportTests).mockResolvedValue({ blob: new Blob(["zip"]), filename: "tests.zip" });
    render(<TransferPortal tests={options} />);
    const button = screen.getByRole("button", { name: "Export selected" });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Select Fictional portable test"));
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(exportTests).toHaveBeenCalledWith([testId]));
  });

  it("requires an explicit import click and renders success", async () => {
    vi.mocked(importTests).mockResolvedValue({ imported_tests: [{ test_id: testId, title: "Imported" }], version_count: 2, asset_count: 3 });
    render(<TransferPortal tests={options} />);
    const file = new File(["zip"], "ielts-tests.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText("Test package ZIP"), { target: { files: [file] } });
    expect(importTests).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(importTests).toHaveBeenCalledWith(file));
    expect(await screen.findByText("Imported 1 test")).toBeInTheDocument();
    expect(screen.getByText(/Practice attempts and history are not included/)).toBeInTheDocument();
  });

  it("renders a structured import failure", async () => {
    vi.mocked(importTests).mockRejectedValue(new Error("bad package"));
    render(<TransferPortal tests={options} />);
    fireEvent.change(screen.getByLabelText("Test package ZIP"), { target: { files: [new File(["x"], "bad.zip")] } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be imported");
  });
});
