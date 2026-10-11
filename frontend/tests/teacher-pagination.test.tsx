import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { listAssignmentResults } from "@/lib/api/classroom-results";
import { listModeration } from "@/lib/api/content-governance";
import { listNotifications } from "@/lib/api/notifications";
import { NotificationCenter } from "@/features/notifications/notification-center";
import { PageNavigation } from "@/features/classrooms/page-navigation";
import { ClassroomResultsPage } from "@/features/classrooms/classroom-result-pages";
import SharedResultsPage from "@/app/classrooms/[classroomId]/assignments/[assignmentId]/results/page";
import ModerationQueuePage from "@/app/admin/moderation/page";
import { serverApiRequest } from "@/lib/api/server-client";
import { renderWithLocale } from "./locale-test-utils";

const mock = vi.hoisted(() => ({ listNotifications: vi.fn(), getUnreadNotificationCount: vi.fn(), markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));
vi.mock("@/lib/api/notifications", async original => ({ ...await original<object>(), ...mock }));
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });
const id = "11111111-1111-4111-8111-111111111111";
it("result and moderation clients preserve explicit limit and offset", async () => {
  const request = vi.fn().mockResolvedValue([]);
  await listAssignmentResults(id, id, request, { limit: 21, offset: 40 });
  expect(request).toHaveBeenCalledWith(`/classrooms/${id}/assignments/${id}/results?limit=21&offset=40`);
  await listModeration(request, "APPROVED", { limit: 21, offset: 60 });
  expect(request).toHaveBeenCalledWith("/admin/test-moderation-requests?status=APPROVED&limit=21&offset=60");
});

it("the results page exposes previous navigation while preserving its authorized route", async () => {
  vi.mocked(serverApiRequest).mockResolvedValue([]);
  render(await ClassroomResultsPage({ params: Promise.resolve({ classroomId: id, assignmentId: id }), namespace: "shared", searchParams: Promise.resolve({ offset: "40" }) }));
  expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", `/classrooms/${id}/assignments/${id}/results?offset=20`);
  expect(serverApiRequest).toHaveBeenCalledWith(`/classrooms/${id}/assignments/${id}/results?limit=21&offset=40`);
});

it("moderation pagination keeps the selected scope status", async () => {
  vi.mocked(serverApiRequest).mockResolvedValue([]);
  render(await ModerationQueuePage({ searchParams: Promise.resolve({ status: "APPROVED", offset: "40" }) }));
  expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/admin/moderation?status=APPROVED&offset=20");
});

it("the role-neutral results route forwards its page offset", async () => {
  vi.mocked(serverApiRequest).mockResolvedValue([]);
  render(await SharedResultsPage({ params: Promise.resolve({ classroomId: id, assignmentId: id }), searchParams: Promise.resolve({ offset: "60" }) }));
  expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", `/classrooms/${id}/assignments/${id}/results?offset=40`);
});

it("page controls preserve filters, localize, and hide unavailable directions", () => {
  const view = renderWithLocale(<PageNavigation path="/admin/moderation?status=REJECTED" offset={0} hasNext />);
  expect(screen.queryByRole("link", { name: "Previous page" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/admin/moderation?status=REJECTED&offset=20");
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  expect(screen.getByRole("link", { name: "Trang tiếp theo" })).toBeInTheDocument();
  view.unmount();
  renderWithLocale(<PageNavigation path="/admin/moderation?status=REJECTED" offset={20} hasNext={false} />);
  expect(screen.getByRole("link", { name: "Trang trước" })).toHaveAttribute("href", "/admin/moderation?status=REJECTED&offset=0");
  expect(screen.queryByRole("link", { name: "Trang tiếp theo" })).not.toBeInTheDocument();
});

it("notification Load more exposes older records without marking them read", async () => {
  const base = { type: "CLASSROOM_INVITED", payload_json: { classroom_name: "Fictional" }, entity_type: "INVITATION", entity_id: id, read_at: null, created_at: "now" };
  mock.listNotifications.mockResolvedValue(Array.from({ length: 20 }, (_, index) => ({ ...base, id: String(index) })));
  mock.getUnreadNotificationCount.mockResolvedValue(30);
  render(<NotificationCenter userId="user" />);
  fireEvent.click(await screen.findByRole("button", { name: "Notifications (30 unread)" }));
  const loadMore = await screen.findByRole("button", { name: "Load more" });
  mock.listNotifications.mockResolvedValue([{ ...base, id: "older", payload_json: { classroom_name: "Older class" } }]);
  fireEvent.click(loadMore);
  await waitFor(() => expect(mock.listNotifications).toHaveBeenCalledWith(undefined, { limit: 20, offset: 20 }));
  expect(await screen.findByText("You were invited to Older class.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Notifications (30 unread)" })).toBeInTheDocument();
  expect(mock.markNotificationRead).not.toHaveBeenCalled();
  expect(mock.markAllNotificationsRead).not.toHaveBeenCalled();
  mock.getUnreadNotificationCount.mockResolvedValue(29);
  fireEvent.click(screen.getAllByRole("button", { name: "Mark read" }).at(-1)!);
  await waitFor(() => expect(mock.markNotificationRead).toHaveBeenCalledWith("older"));
  expect(await screen.findByRole("button", { name: "Notifications (29 unread)" })).toBeInTheDocument();
  expect(screen.getByText("You were invited to Older class.")).toBeInTheDocument();
  expect(mock.listNotifications).toHaveBeenCalledTimes(3);
});

it("notification pagination advances by fetched rows when an overlapping item is deduplicated", async () => {
  const base = { type: "CLASSROOM_INVITED", payload_json: { classroom_name: "Fictional" }, entity_type: "INVITATION", entity_id: id, read_at: null, created_at: "now" };
  mock.listNotifications.mockResolvedValue(Array.from({ length: 20 }, (_, index) => ({ ...base, id: String(index) })));
  mock.getUnreadNotificationCount.mockResolvedValue(30);
  render(<NotificationCenter userId="user" />);
  fireEvent.click(await screen.findByRole("button", { name: "Notifications (30 unread)" }));
  const first = await screen.findByRole("button", { name: "Load more" });
  mock.listNotifications.mockResolvedValue(Array.from({ length: 20 }, (_, index) => ({ ...base, id: String(index + 19) })));
  fireEvent.click(first);
  await waitFor(() => expect(mock.listNotifications).toHaveBeenCalledWith(undefined, { limit: 20, offset: 20 }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Load more" })).toBeEnabled());
  mock.listNotifications.mockResolvedValue([]);
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  await waitFor(() => expect(mock.listNotifications).toHaveBeenCalledWith(undefined, { limit: 20, offset: 40 }));
});

it("notification client requests older rows with limit/offset", async () => {
  // The component mocks its client above; inspect the real module for this contract.
  const actual = await vi.importActual<typeof import("@/lib/api/notifications")>("@/lib/api/notifications");
  const request = vi.fn().mockResolvedValue({ items: [] });
  await actual.listNotifications(request, { limit: 20, offset: 100 });
  expect(request).toHaveBeenCalledWith("/notifications?limit=20&offset=100");
  expect(listNotifications).toBeDefined();
});
