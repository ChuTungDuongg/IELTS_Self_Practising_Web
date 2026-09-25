import { expect, it, vi } from "vitest";
import { deleteTestSession } from "@/lib/api/test-sessions";
import type { ApiRequester } from "@/lib/api/client";

it("deletes one Full Mock session through the shared API client", async () => {
  const request = vi.fn().mockResolvedValue(undefined) as unknown as ApiRequester;
  const sessionId = "99999999-9999-4999-8999-999999999999";

  await deleteTestSession(sessionId, request);

  expect(request).toHaveBeenCalledWith(`/test-sessions/${sessionId}`, { method: "DELETE" });
});
