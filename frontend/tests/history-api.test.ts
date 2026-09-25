import { expect, it, vi } from "vitest";
import { deleteStandaloneTestHistory } from "@/lib/api/history";
import type { ApiRequester } from "@/lib/api/client";

it("deletes standalone history for one exact version through the shared API client", async () => {
  const request = vi.fn().mockResolvedValue(undefined) as unknown as ApiRequester;
  const versionId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

  await deleteStandaloneTestHistory(versionId, request);

  expect(request).toHaveBeenCalledWith(
    `/history/test-versions/${versionId}/standalone-attempts`,
    { method: "DELETE" },
  );
});
