import { expect, it, vi } from "vitest";
import { SpeakingChunkTransport } from "@/features/speaking/speaking-transport";

it("retries identical sequence and waits for final acknowledgement", async () => {
  let acknowledge!: () => void;
  const upload = vi.fn().mockRejectedValueOnce(new Error("offline")).mockImplementationOnce(() => new Promise<void>((resolve) => { acknowledge = resolve; }));
  const close = vi.fn().mockResolvedValue(undefined);
  const queue = new SpeakingChunkTransport(upload, close, () => undefined);
  const blob = new Blob(["fictional"]); queue.enqueue(blob);
  const flushed = queue.close();
  await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
  expect(upload.mock.calls[0]).toEqual([0, blob]); expect(upload.mock.calls[1]).toEqual([0, blob]);
  expect(close).not.toHaveBeenCalled(); acknowledge(); await flushed; expect(close).toHaveBeenCalledWith(1);
});
it("failed upload remains available to retry without dropping later data", async () => {
  const upload = vi.fn().mockRejectedValue(new Error("offline"));
  const queue = new SpeakingChunkTransport(upload, vi.fn(), () => undefined);
  queue.enqueue(new Blob(["first"])); queue.enqueue(new Blob(["second"]));
  await expect(queue.flush()).rejects.toThrow(); upload.mockResolvedValue(undefined);
  await queue.flush(); expect(upload.mock.calls.at(-2)?.[0]).toBe(0); expect(upload.mock.calls.at(-1)?.[0]).toBe(1);
});
it("retries a failed segment ACK without uploading acknowledged chunks again", async () => {
  const upload = vi.fn().mockResolvedValue(undefined); const close = vi.fn().mockRejectedValueOnce(new Error("lost acknowledgement")).mockResolvedValue(undefined);
  const queue = new SpeakingChunkTransport(upload, close, () => undefined);
  queue.enqueue(new Blob(["accepted"])); await expect(queue.close()).rejects.toThrow(); await queue.close();
  expect(upload).toHaveBeenCalledTimes(1); expect(close).toHaveBeenCalledTimes(2);
});
