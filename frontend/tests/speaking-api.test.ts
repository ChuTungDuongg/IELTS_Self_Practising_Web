import { expect, it, vi } from "vitest";
import { getAnalytics } from "@/lib/api/analytics";
import { speakingStateSchema, fetchSpeakingAudio } from "@/lib/api/speaking";

it("keeps existing analytics readable with unscored Speaking attempt metadata", async () => {
  const request = vi.fn().mockResolvedValue({ total_finalized_attempts: 1, total_active_seconds: 60, average_attempt_seconds: 60, bands: {}, completed_full_mocks: 0, latest_project_overall: null, latest_full_mock: null, trends: [], question_types: [], weak_areas: [], content_timing: [], attempts: [{ attempt_id: "11111111-1111-4111-8111-111111111111", skill: "SPEAKING", label: "Fictional Speaking", band_score: null, finished_at: "2026-10-12T00:01:00Z" }] });
  expect((await getAnalytics(undefined, request)).attempts[0].band_score).toBeNull();
});
it("rejects non-private playback paths before requesting data", async () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  try { await expect(fetchSpeakingAudio("/assets/secret/content")).rejects.toThrow("SPEAKING_MEDIA_INVALID"); expect(fetch).not.toHaveBeenCalled(); }
  finally { vi.unstubAllGlobals(); }
});
it("requires an authorized seven-second grace contract", () => {
  expect(speakingStateSchema.shape.recovery_grace_seconds.safeParse(8).success).toBe(false);
  expect(speakingStateSchema.shape.recovery_grace_seconds.parse(7)).toBe(7);
});
