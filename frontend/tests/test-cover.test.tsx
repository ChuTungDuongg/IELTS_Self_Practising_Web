import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CoverManager, CoverThumbnail } from "@/features/test-builder/test-cover";
import { getTest, removeTestCover, uploadTestCover } from "@/lib/api/tests";
import { renderWithLocale } from "./locale-test-utils";

vi.mock("@/lib/api/tests", () => ({ getTest: vi.fn(), removeTestCover: vi.fn(), uploadTestCover: vi.fn() }));
const cover = { id: "22222222-2222-4222-8222-222222222222", content_url: "/tests/11111111-1111-4111-8111-111111111111/cover/22222222-2222-4222-8222-222222222222/content", mime_type: "image/png" as const };
const replacement = { ...cover, id: "33333333-3333-4333-8333-333333333333", content_url: cover.content_url.replace(cover.id, "33333333-3333-4333-8333-333333333333") };
const testId = "11111111-1111-4111-8111-111111111111";

beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

it("previews, uploads once, refreshes and removes the saved cover", async () => {
  let finish!: (value: typeof replacement) => void;
  vi.mocked(uploadTestCover).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  vi.mocked(getTest).mockResolvedValue({ cover_image: replacement } as Awaited<ReturnType<typeof getTest>>);
  vi.mocked(removeTestCover).mockResolvedValue(undefined);
  renderWithLocale(<CoverManager testId={testId} initialCover={cover} title="Fictional" />);
  expect(screen.getByRole("img", { name: "Cover for Fictional" })).toHaveAttribute("src", expect.stringContaining(cover.content_url));
  const file = new File(["image"], "cover.png", { type: "image/png" });
  fireEvent.change(screen.getByLabelText("Choose cover image"), { target: { files: [file] } });
  expect(screen.getByRole("img", { name: "Selected image preview" })).toHaveAttribute("src", "blob:preview");
  fireEvent.click(screen.getByRole("button", { name: "Upload cover" }));
  expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
  expect(uploadTestCover).toHaveBeenCalledOnce();
  await act(async () => { finish(replacement); });
  expect(await screen.findByRole("status")).toHaveTextContent("Cover saved.");
  expect(screen.getByRole("img", { name: "Cover for Fictional" })).toHaveAttribute("src", expect.stringContaining(replacement.id));
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  vi.mocked(getTest).mockResolvedValue({ cover_image: null } as Awaited<ReturnType<typeof getTest>>);
  fireEvent.click(screen.getByRole("button", { name: "Remove cover" }));
  await waitFor(() => expect(removeTestCover).toHaveBeenCalledExactlyOnceWith(testId));
  expect(await screen.findByRole("status")).toHaveTextContent("Cover removed.");
  expect(screen.queryByRole("img", { name: "Cover for Fictional" })).not.toBeInTheDocument();
});

it("keeps the saved cover on upload failure and localizes controls", async () => {
  vi.mocked(uploadTestCover).mockRejectedValue(new Error("Upload rejected"));
  renderWithLocale(<CoverManager testId={testId} initialCover={cover} title="Fictional" />);
  fireEvent.change(screen.getByLabelText("Choose cover image"), { target: { files: [new File(["x"], "bad.png", { type: "image/png" })] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload cover" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Upload rejected");
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByLabelText("Chọn ảnh bìa")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Xóa ảnh bìa" })).toBeInTheDocument();
});

it("uses a neutral fallback when no cover is available or the image fails", () => {
  const view = render(<CoverThumbnail title="Fictional" cover={cover} />);
  fireEvent.error(screen.getByRole("img", { name: "Cover for Fictional" }));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(view.container.querySelector("svg")).toBeInTheDocument();
});
