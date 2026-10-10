import { afterEach, expect, it, vi } from "vitest";
import { attemptResponseSchema, startAttempt } from "@/lib/api/attempts";
import { getHistory } from "@/lib/api/history";

const id = "11111111-1111-4111-8111-111111111111";
const unit = { kind: "READING_PASSAGE", id, order_index: 1, label: "Passage 2", title: "Fictional passage" };
const response = { attempt_id: id, test_version_id: id, module: "READING", status: "IN_PROGRESS", finished_reason: null, timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: "2026-10-10T00:00:00Z", paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: "2026-10-10T00:00:00Z", finished_at: null, elapsed_seconds: 0, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: "2026-10-10T00:00:00Z" };

afterEach(() => vi.unstubAllGlobals());

it("preserves focused scope metadata while accepting legacy attempt responses", () => {
  expect(attemptResponseSchema.parse(response).attempt_id).toBe(id);
  expect(attemptResponseSchema.parse({ ...response, scope: "FOCUSED_UNIT", focused_unit: unit }).focused_unit).toEqual(unit);
});

it("leaves existing full-module start requests unchanged", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...response, scope: "FULL_MODULE", focused_unit: null })));
  vi.stubGlobal("fetch", fetchMock);
  const input = { test_version_id: id, module: "READING", timer: { mode: "COUNT_UP" } } as const;
  expect((await startAttempt(input)).scope).toBe("FULL_MODULE");
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(input);
});

it("retains focused identity in history without constructing full-test group slots", async () => {
  const item = { ...response, test_id: id, test_title: "Fictional test", version_number: 1, scope: "FOCUSED_UNIT", focused_unit: unit };
  const request = vi.fn().mockResolvedValue({ items: [item], groups: [], total: 1 });
  const history = await getHistory(request);
  expect(history.items[0].focused_unit).toEqual(unit);
  expect(history.groups).toEqual([]);
});

it("preserves the task score separately from the intentionally null Writing band", async () => {
  const item = { ...response, module: "WRITING", test_id: id, test_title: "Fictional test", version_number: 1, scope: "FOCUSED_UNIT", task_score: 6.75,
    focused_unit: { ...unit, kind: "WRITING_TASK", label: "Task 1", title: null } };
  const request = vi.fn().mockResolvedValue({ items: [item], groups: [], total: 1 });
  const history = await getHistory(request);
  expect(history.items[0].task_score).toBe(6.75);
  expect(history.items[0].band_score).toBeNull();
});
