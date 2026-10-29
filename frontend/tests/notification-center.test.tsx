import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { NotificationCenter } from "@/features/notifications/notification-center";
import { renderWithLocale } from "./locale-test-utils";
const api = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  getUnreadNotificationCount: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn()
}));
vi.mock("@/lib/api/notifications", () => api);
const item = {
  id: "notice",
  type: "CLASSROOM_INVITED",
  payload_json: { classroom_name: "Evening class" },
  entity_type: "INVITATION",
  entity_id: "invite",
  read_at: null,
  created_at: "2026-10-11T08:00:00Z"
};
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  api.listNotifications.mockResolvedValue([item]);
  api.getUnreadNotificationCount.mockResolvedValue(1);
  api.markNotificationRead.mockResolvedValue(undefined);
  api.markAllNotificationsRead.mockResolvedValue(undefined);
});
it("shows unread count and opening the list does not mark anything read", async () => {
  renderWithLocale(<NotificationCenter userId="user" />);
  const bell = await screen.findByRole("button", { name: "Notifications (1 unread)" });
  expect(api.listNotifications).not.toHaveBeenCalled();
  fireEvent.click(bell);
  expect(await screen.findByText("You were invited to Evening class.")).toBeInTheDocument();
  expect(api.listNotifications).toHaveBeenCalledOnce();
  expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/classrooms");
  expect(api.markNotificationRead).not.toHaveBeenCalled();
  expect(api.markAllNotificationsRead).not.toHaveBeenCalled();
});
it("does not let a delayed initial count overwrite the refreshed count", async () => {
  let resolveInitial!: (count: number) => void;
  api.getUnreadNotificationCount.mockReset()
    .mockReturnValueOnce(new Promise<number>(resolve => { resolveInitial = resolve; }))
    .mockResolvedValue(4);
  renderWithLocale(<NotificationCenter userId="user" />);
  fireEvent.click(screen.getByRole("button", { name: "Notifications (0 unread)" }));
  await screen.findByRole("button", { name: "Notifications (4 unread)" });
  await act(async () => { resolveInitial(1); });
  expect(screen.getByRole("button", { name: "Notifications (4 unread)" })).toBeInTheDocument();
});
it("retries a failed initial count when the panel is opened", async () => {
  api.getUnreadNotificationCount.mockReset().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(2);
  renderWithLocale(<NotificationCenter userId="user" />);
  await waitFor(() => expect(api.getUnreadNotificationCount).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Notifications (0 unread)" }));
  expect(await screen.findByRole("button", { name: "Notifications (2 unread)" })).toBeInTheDocument();
  expect(await screen.findByText("You were invited to Evening class.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("marks one and all only through explicit actions and refetches count", async () => {
  renderWithLocale(<NotificationCenter userId="user" />);
  fireEvent.click(await screen.findByRole("button", { name: "Notifications (1 unread)" }));
  fireEvent.click(await screen.findByRole("button", { name: "Mark read" }));
  await waitFor(() => expect(api.markNotificationRead).toHaveBeenCalledWith("notice"));
  fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
  await waitFor(() => expect(api.markAllNotificationsRead).toHaveBeenCalledOnce());
  expect(api.getUnreadNotificationCount.mock.calls.length).toBeGreaterThan(1);
});
it("localizes stored event data in Vietnamese", async () => {
  renderWithLocale(<NotificationCenter userId="user" />);
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  fireEvent.click(await screen.findByRole("button", { name: "Thông báo (1 chưa đọc)" }));
  expect(await screen.findByText("Bạn được mời vào lớp Evening class.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Đánh dấu đã đọc tất cả" })).toBeInTheDocument();
});
it("opens a published announcement in its classroom and localizes its event", async () => {
  api.listNotifications.mockResolvedValue([{ ...item,
    type: "CLASSROOM_ANNOUNCEMENT_PUBLISHED",
    entity_type: "CLASSROOM_POST", entity_id: "post-id",
    payload_json: { classroom_name: "Evening class", classroom_id: "classroom-id" },
  }]);
  renderWithLocale(<NotificationCenter userId="user" />);
  fireEvent.click(await screen.findByRole("button", { name: "Notifications (1 unread)" }));
  expect(await screen.findByText("A new announcement was published in Evening class.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/classrooms/classroom-id?post=post-id");
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  expect(await screen.findByText("Lớp Evening class có thông báo mới.")).toBeInTheDocument();
});
it("a changed recipient starts a fresh notification panel without flashing previous content", async () => {
  const view = renderWithLocale(<NotificationCenter key="first" userId="first" />);
  fireEvent.click(await screen.findByRole("button", { name: "Notifications (1 unread)" }));
  await screen.findByText("You were invited to Evening class.");
  api.listNotifications.mockReturnValue(new Promise(() => { }));
  api.getUnreadNotificationCount.mockReturnValue(new Promise(() => { }));
  view.rerender(<NotificationCenter key="second" userId="second" />);
  expect(screen.queryByText("You were invited to Evening class.")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Notifications (0 unread)" })).toHaveAttribute("aria-expanded", "false");
});
