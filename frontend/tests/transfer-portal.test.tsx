import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import TransferPage from "@/app/transfer/page";
import { TransferPortal } from "@/features/transfer/transfer-portal";
import { exportTests, importTests } from "@/lib/api/transfer";
import { getTests } from "@/lib/api/tests";

vi.mock("next/navigation", () => ({ usePathname: () => "/transfer" }));
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
    vi.clearAllMocks();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:test"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("adds Transfer to primary navigation", () => {
    render(<AppShell><p>content</p></AppShell>);
    expect(screen.getByRole("link", { name: "Transfer" })).toHaveAttribute("href", "/transfer");
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
