import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { StartSpeaking } from "@/features/speaking/start-speaking";
import { startAttempt } from "@/lib/api/attempts";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/attempts", () => ({ startAttempt: vi.fn().mockResolvedValue({ attempt_id: "fictional" }) }));
beforeEach(() => vi.clearAllMocks());
it("starts in practice mode without changing authored prompt timing", async () => {
  render(<StartSpeaking versionId="version" />);
  expect(screen.getByLabelText("Speaking mode")).toHaveValue("PRACTICE");
  fireEvent.click(screen.getByText("Start Speaking"));
  await waitFor(() => expect(startAttempt).toHaveBeenCalledWith({ test_version_id: "version", module: "SPEAKING", speaking_mode: "PRACTICE", timer: { mode: "COUNT_UP" } }));
});
it("starts an explicit exam with authored prompt timing", async () => {
  render(<StartSpeaking versionId="version" />);
  fireEvent.change(screen.getByLabelText("Speaking mode"), { target: { value: "EXAM" } });
  fireEvent.click(screen.getByText("Start Speaking"));
  await waitFor(() => expect(startAttempt).toHaveBeenCalledWith({ test_version_id: "version", module: "SPEAKING", speaking_mode: "EXAM", timer: { mode: "COUNT_UP" } }));
});
