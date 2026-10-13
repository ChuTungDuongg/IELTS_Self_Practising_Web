import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import ReviewShellPage from "@/app/review/[attemptId]/page";
import { getExam } from "@/lib/api/exam";
import { getSpeakingReview } from "@/lib/api/speaking";

vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("NOT_FOUND"); } }));
vi.mock("@/lib/api/exam", async original => ({ ...await original<typeof import("@/lib/api/exam")>(), getExam: vi.fn() }));
vi.mock("@/lib/api/speaking", async original => ({ ...await original<typeof import("@/lib/api/speaking")>(), getSpeakingReview: vi.fn() }));
vi.mock("@/features/speaking/speaking-review", () => ({ SpeakingReview: () => <p>Speaking review selected</p> }));
const attemptId = "11111111-1111-4111-8111-111111111111";
beforeEach(() => { vi.clearAllMocks(); vi.mocked(getExam).mockResolvedValue({ attempt: { module: "SPEAKING", status: "SUBMITTED" } } as never); });
it("loads the authorized Speaking review DTO through the server client", async () => {
  vi.mocked(getSpeakingReview).mockResolvedValue({ parts: [] } as never);
  render(await ReviewShellPage({ params: Promise.resolve({ attemptId }) }));
  expect(getSpeakingReview).toHaveBeenCalledExactlyOnceWith(attemptId, expect.any(Function));
  expect(screen.getByText("Speaking review selected")).toBeInTheDocument();
});
it("uses the existing unavailable review boundary on a denied Speaking response", async () => {
  vi.mocked(getSpeakingReview).mockRejectedValue(new Error("private persistence details"));
  await expect(ReviewShellPage({ params: Promise.resolve({ attemptId }) })).rejects.toThrow("NOT_FOUND");
});
