import { expect, it, vi } from "vitest";
import { deleteStandaloneTestHistory, getHistory } from "@/lib/api/history";
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
it("keeps history readable when a new Speaking attempt is present", async () => {
  const item = { attempt_id: "11111111-1111-4111-8111-111111111111", test_id: "22222222-2222-4222-8222-222222222222", test_version_id: "33333333-3333-4333-8333-333333333333", test_title: "Fictional history", version_number: 1, module: "SPEAKING", status: "SUBMITTED", started_at: "2026-10-12T00:00:00Z", finished_at: "2026-10-12T00:01:00Z", elapsed_seconds: 60, timer_mode: "COUNT_UP", timer_limit_seconds: null, remaining_seconds: null, raw_score: null, max_score: null, band_score: null };
  const request = vi.fn().mockResolvedValue({ items: [item], groups: [], sessions: [], total: 1 });
  expect((await getHistory(request)).items[0].module).toBe("SPEAKING");
});
