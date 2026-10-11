import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "@/lib/api/client";
import { listClassrooms, listAssignments, startAssignment } from "@/lib/api/classrooms";
import { listNotifications, getUnreadNotificationCount } from "@/lib/api/notifications";
import { getAssignmentResult } from "@/lib/api/classroom-results";
import { getTests, getVersion } from "@/lib/api/tests";
vi.mock("@/lib/api/client", async (original) => ({ ...await original<object>(), apiRequest: vi.fn() }));
const id = "11111111-1111-4111-8111-111111111111";
beforeEach(() => vi.resetAllMocks());
it("sends public practice eligibility queries without changing Builder defaults", async () => {
  vi.mocked(apiRequest).mockResolvedValue([]);
  await getTests({ publicOnly: true });
  expect(apiRequest).toHaveBeenLastCalledWith("/tests?public_only=true");
  await getTests();
  expect(apiRequest).toHaveBeenLastCalledWith("/tests");
  await getTests({ archived: true, publicOnly: true });
  expect(apiRequest).toHaveBeenLastCalledWith("/tests?archived=true&public_only=true");
  vi.mocked(apiRequest).mockResolvedValue({
    id, test_id: id, test_title: "Fictional", version_number: 1, status: "PUBLISHED",
    created_at: "now", published_at: "now", modules: [],
  });
  await getVersion(id, apiRequest, { publicOnly: true });
  expect(apiRequest).toHaveBeenLastCalledWith(`/test-versions/${id}?public_only=true`);
});
it("parses wrapped classroom/notification lists and bare assignment arrays", async () => {
  const classroom = {
    id,
    teacher_id: id,
    name: "Fictional class",
    description: null,
    status: "ACTIVE",
    archived_at: null,
    created_at: "now",
    updated_at: "now"
  };
  vi.mocked(apiRequest).mockResolvedValueOnce({ items: [classroom] }).mockResolvedValueOnce([]).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({ unread_count: 3 });
  expect(await listClassrooms()).toEqual([classroom]);
  expect(await listAssignments(id)).toEqual([]);
  expect(await listNotifications()).toEqual([]);
  expect(await getUnreadNotificationCount()).toBe(3);
});
it("starts focused assignments using existing focused_unit identity and full mock provenance endpoints", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ attempt_id: id, test_session_id: null });
  const input = {
    mode: "MODULE" as const,
    module: "WRITING" as const,
    scope: "FOCUSED_UNIT" as const,
    focused_unit: { kind: "WRITING_TASK" as const, id },
    timer: { mode: "COUNT_UP" as const }
  };
  await startAssignment(id, input);
  expect(apiRequest).toHaveBeenCalledWith(`/classroom-assignments/${id}/start`, { method: "POST", body: JSON.stringify(input) });
  expect(JSON.parse(vi.mocked(apiRequest).mock.calls[0][1]!.body as string)).not.toHaveProperty("classroom_assignment_id");
});
it("rejects malformed nested teacher reviews rather than trusting a cast", async () => {
  const attempt = {
    attempt_id: id,
    test_version_id: id,
    module: "WRITING",
    status: "SUBMITTED",
    finished_reason: "USER_SUBMIT",
    timer_mode: "COUNT_UP",
    timer_limit_seconds: null,
    started_at: "now",
    last_active_at: "now",
    finished_at: "now",
    paused_at: null,
    total_paused_seconds: 0,
    deadline_at: null,
    elapsed_seconds: 1,
    remaining_seconds: null,
    raw_score: null,
    max_score: null,
    band_score: null,
    server_time: "now"
  };
  vi.mocked(apiRequest).mockResolvedValue({
    student_id: id,
    student_display_name: "Student",
    attempt,
    session_id: null,
    reading_review: null,
    listening_review: null,
    writing_review: { tasks: "invalid" },
    ai_runs: [],
    submitted_answers: [],
    writing_responses: []
  });
  await expect(getAssignmentResult(id, id, id)).rejects.toThrow();
});
