import { beforeEach, expect, it, vi } from "vitest";
import { ClassroomOverviewPage } from "@/features/classrooms/overview/classroom-overview-page";

const api = vi.hoisted(() => ({ request: vi.fn(), room: vi.fn(), assignments: vi.fn(), feed: vi.fn(), calendar: vi.fn(), members: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: api.request }));
vi.mock("@/lib/api/auth", () => ({ userSchema: { parse: (value: unknown) => value } }));
vi.mock("@/lib/api/classroom-learning", () => ({ dashboardSchema: { parse: (value: unknown) => value } }));
vi.mock("@/lib/api/classrooms", () => ({ getClassroom: api.room, listAssignments: api.assignments, listMemberPreview: api.members }));
vi.mock("@/lib/api/classroom-content", () => ({ listFeed: api.feed }));
vi.mock("@/lib/api/assignment-scheduling", () => ({ getAssignmentCalendar: api.calendar }));

const room = { id: "room", teacher_id: "owner", name: "Class", status: "ACTIVE", capabilities: [], classroom_role: "STUDENT" };
beforeEach(() => { vi.clearAllMocks(); api.room.mockResolvedValue(room); api.request.mockResolvedValue({ id: "student", role: "USER" }); api.assignments.mockResolvedValue([]); api.feed.mockResolvedValue({ items: [] }); api.calendar.mockResolvedValue({ items: [], total: 0 }); api.members.mockResolvedValue([]); });

it("loads only authorized summaries for a student and never requests analytics or a roster", async () => {
  await ClassroomOverviewPage({ params: Promise.resolve({ classroomId: "room" }) });
  expect(api.request.mock.calls.map(call => call[0])).toEqual(["/auth/me"]);
  expect(api.calendar).toHaveBeenCalledOnce();
  expect(api.feed).toHaveBeenCalledOnce();
  expect(api.members).not.toHaveBeenCalled();
});

it("requests a bounded member preview only for an authorized roster viewer", async () => {
  api.room.mockResolvedValue({ ...room, capabilities: ["roster.view"] });
  await ClassroomOverviewPage({ params: Promise.resolve({ classroomId: "room" }) });
  expect(api.members).toHaveBeenCalledWith("room", api.request);
});

it("does not request dashboard data when classroom access fails", async () => {
  api.room.mockRejectedValue(new Error("not found"));
  await expect(ClassroomOverviewPage({ params: Promise.resolve({ classroomId: "missing" }) })).rejects.toThrow("not found");
  expect(api.assignments).not.toHaveBeenCalled();
  expect(api.feed).not.toHaveBeenCalled();
  expect(api.calendar).not.toHaveBeenCalled();
});
