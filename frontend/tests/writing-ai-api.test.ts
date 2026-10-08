import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, resetAuthRequestStateForTests } from "@/lib/api/client";
import { cancelAIWritingRun, isCancelledAIRun } from "@/lib/api/writing-ai";

const runId = "11111111-1111-4111-8111-111111111111";
const cancelled = {
  id: runId, attempt_id: runId, writing_task_id: runId, status: "FAILED",
  provider: "fake", model: "fake", prompt_version: "mts-task2-v7",
  result: null, progress: {}, error_code: "AI_GRADING_CANCELLED", error_message: "Bạn đã dừng bài chấm AI.",
  started_at: null, completed_at: "2026-10-09T00:00:00Z", created_at: "2026-10-09T00:00:00Z",
};

beforeEach(() => resetAuthRequestStateForTests());
afterEach(() => vi.unstubAllGlobals());

it("posts cancellation with normal cookie auth and validates the existing FAILED response", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(cancelled), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const run = await cancelAIWritingRun(runId);
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock.mock.calls[0][0]).toBe(`http://localhost:8000/api/v1/ai-writing-grading-runs/${runId}/cancel`);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", credentials: "include", cache: "no-store" });
  expect(run.status).toBe("FAILED");
  expect(isCancelledAIRun(run)).toBe(true);
  expect(isCancelledAIRun({ ...run, error_code: "AI_PROVIDER_TIMEOUT" })).toBe(false);
});

it("rejects a new database status instead of silently changing the API contract", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...cancelled, status: "CANCELLED" }), { status: 200 })));
  await expect(cancelAIWritingRun(runId)).rejects.toThrow();
});

it("preserves authorization failures from the normal API client", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "AI_RUN_NOT_FOUND", message: "Không tìm thấy bài đánh giá AI này." }), { status: 404 })));
  await expect(cancelAIWritingRun(runId)).rejects.toBeInstanceOf(ApiError);
});
