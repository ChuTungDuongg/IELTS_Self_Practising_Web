import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SpeakingReview } from "@/features/speaking/speaking-review";
import * as api from "@/lib/api/speaking";
vi.mock("@/lib/api/speaking", () => ({ fetchSpeakingAudio: vi.fn() }));
vi.mock("@/lib/api/speaking-transcript", () => ({ latestTranscriptRun: vi.fn().mockResolvedValue(null), activeTranscript: () => false }));
const data = { attempt_id: "a", test_title: "Fictional review", parts: [{ part_number: 1, responses: [{ prompt: { id: "p", prompt_text: "Fictional reviewed question", config_json: {}, part_number: 1 }, response: { id: "r", duration_ms: 31000, completion_reason: "USER_DONE", status: "COMPLETED" }, segments: [{ id: "s", content_url: "/speaking-attempts/a/segments/s/content", mime_type: "audio/webm", chunks: [{ byte_size: 10 }] }] }] }] } as unknown as api.SpeakingReviewData;
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:private", revokeObjectURL: vi.fn() }); });
afterEach(() => vi.unstubAllGlobals());
it("groups authored responses and plays authorized audio by prompt", async () => {
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["private"])); render(<SpeakingReview data={data} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording"));
  expect(await screen.findByLabelText("Recording segment 1")).toHaveAttribute("src", "blob:private");
  expect(screen.getByText("31 s")).toBeInTheDocument(); expect(screen.getByText("Generate Transcript")).toBeInTheDocument(); expect(screen.queryByText("Grade with AI")).toBeNull();
});
it("displays safe authorization error", async () => {
  vi.mocked(api.fetchSpeakingAudio).mockRejectedValue(new Error("secret internal path")); render(<SpeakingReview data={data} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Recording access"); expect(screen.queryByText("secret internal path")).toBeNull();
});
it("loads only the selected response's physical segments", async () => {
  const second = { ...data.parts[0].responses[0], response: { ...data.parts[0].responses[0].response, id: "r2" }, prompt: { ...data.parts[0].responses[0].prompt, id: "p2", prompt_text: "Fictional second question" }, segments: [{ ...data.parts[0].responses[0].segments[0], id: "s2", content_url: "/speaking-attempts/a/segments/s2/content" }] };
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["second"])); render(<SpeakingReview data={{ ...data, parts: [{ ...data.parts[0], responses: [...data.parts[0].responses, second] }] }} />);
  const summary = screen.getByText("Fictional second question"); fireEvent.click(summary);
  fireEvent.click(within(summary.parentElement!).getByText("Load recording"));
  expect(await screen.findByLabelText("Recording segment 1")).toBeInTheDocument();
  expect(api.fetchSpeakingAudio).toHaveBeenCalledExactlyOnceWith("/speaking-attempts/a/segments/s2/content");
});
it("does not retain a playback URL when download finishes after unmount", async () => {
  let finish!: (blob: Blob) => void; vi.mocked(api.fetchSpeakingAudio).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const create = vi.spyOn(URL, "createObjectURL"); const view = render(<SpeakingReview data={data} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording")); view.unmount();
  await act(async () => finish(new Blob(["private"]))); expect(create).not.toHaveBeenCalled();
});
