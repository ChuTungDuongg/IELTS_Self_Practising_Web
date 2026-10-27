import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AssignmentList } from "@/features/classrooms/assignment-list";
import { AssignmentStatus } from "@/features/classrooms/assignments/assignment-status";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { renderWithLocale } from "./locale-test-utils";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
const api = vi.hoisted(() => ({ monitoring: vi.fn(), updateAssignmentSchedule: vi.fn() }));
vi.mock("@/lib/api/assignment-scheduling", async original => ({ ...await original<object>(), updateAssignmentSchedule: api.updateAssignmentSchedule }));
vi.mock("@/features/classrooms/scheduling/assignment-monitoring", () => ({ AssignmentMonitoringPanel: (props: unknown) => { api.monitoring(props); return <p>Loaded monitoring</p>; } }));
const item = (id: string, title: string, status: "ACTIVE" | "ARCHIVED" = "ACTIVE"): ClassroomAssignment => ({ id, title, status, classroom_id: "room", test_version_id: "version", created_by_user_id: "teacher", note: null, created_at: "now", archived_at: status === "ARCHIVED" ? "2026-10-01T00:00:00Z" : null, target: { mode: "MODULE", module: "WRITING", scope: "FULL_MODULE" } });
const items = [item("one", "Đề ôn tập"), item("two", "Weekly practice"), item("old", "Archived writing", "ARCHIVED")];
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("groups actual active and archived records with correct counts and lazy details", () => {
  renderWithLocale(<AssignmentList assignments={items} canViewResults canStart={false} canSchedule canArchive onChanged={vi.fn()} />);
  expect(screen.getByRole("region", { name: "Active assignments" })).toHaveTextContent("2 assignments");
  expect(screen.getByRole("region", { name: "Archived assignments" })).toHaveTextContent("1 assignment");
  expect(api.monitoring).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Đề ôn tập" }));
  fireEvent.click(within(screen.getByRole("region", { name: "View details · Đề ôn tập" })).getByRole("button", { name: "Monitor submissions" }));
  expect(screen.getByText("Loaded monitoring")).toBeInTheDocument();
});

it("searches Vietnamese text and filters archive status without refetching or clearing search", () => {
  renderWithLocale(<AssignmentList assignments={items} canViewResults canStart={false} />);
  const search = screen.getByRole("searchbox", { name: "Search assignments" });
  fireEvent.change(search, { target: { value: "DE ON TAP" } });
  expect(screen.getByRole("button", { name: "Đề ôn tập" })).toBeInTheDocument();
  expect(screen.queryByText("Weekly practice")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Đề ôn tập" }));
  expect(search).toHaveValue("DE ON TAP");
  fireEvent.change(screen.getByLabelText("Assignment status"), { target: { value: "ARCHIVED" } });
  expect(screen.getByText("No assignments match this search or filter.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear assignment search" }));
  expect(screen.queryByRole("region", { name: "Active assignments" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Archived writing" })).toBeInTheDocument();
});

it("keeps observer archives readable with no management actions", () => {
  const { container } = renderWithLocale(<AssignmentList assignments={items} canViewResults canStart={false} />);
  const archived = screen.getByRole("region", { name: "Archived assignments" });
  expect(within(archived).getByRole("button", { name: "View details" })).toBeInTheDocument();
  expect(within(archived).queryByRole("button", { name: /Restore|Delete/ })).not.toBeInTheDocument();
  expect(screen.queryByText("More actions")).not.toBeInTheDocument();
  expect(container.querySelector(".assignments-creation")).toBeNull();
  expect(screen.queryByRole("button", { name: "Start assignment" })).not.toBeInTheDocument();
});

it("uses one desktop creation panel, result navigation, and an accessible schedule disclosure", () => {
  const { container } = renderWithLocale(<AssignmentList assignments={[items[0]]} canViewResults canStart={false} canSchedule creationForm={<form aria-label="Creation form"><input aria-label="Test choice" /></form>} />);
  expect(container.querySelector(".assignments-layout")).toHaveAttribute("data-creation", "true");
  expect(screen.getAllByRole("form", { name: "Creation form" })).toHaveLength(1);
  expect(screen.getByRole("link", { name: "Results" })).toHaveAttribute("href", "/teacher/classrooms/room/assignments/one/results");
  fireEvent.click(screen.getByText("More actions"));
  fireEvent.click(screen.getByRole("button", { name: "Edit schedule" }));
  expect(screen.getByLabelText("Maximum starts")).toBeInTheDocument();
  expect(api.monitoring).not.toHaveBeenCalled();
});

it("collapses the mobile form and reveals/focuses that same form for a header create request", async () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const props = { assignments: [], canStart: false, canSchedule: true, creationForm: <form aria-label="Creation form"><input aria-label="Test choice" /></form> };
  const view = renderWithLocale(<AssignmentList {...props} />);
  expect(screen.getByRole("button", { name: "Create assignment" })).toHaveAttribute("aria-expanded", "false");
  const form = screen.getByRole("form", { name: "Creation form", hidden: true });
  expect(form).not.toBeVisible();
  view.rerender(<AssignmentList {...props} creationRequest={1} />);
  await waitFor(() => expect(screen.getByLabelText("Test choice")).toHaveFocus());
  expect(screen.getByRole("form", { name: "Creation form" })).toBe(form);
  expect(screen.getByRole("button", { name: "Create assignment" })).toHaveAttribute("aria-expanded", "true");
});

it("does not mount a supplied form without assignment permissions and translates empty states", () => {
  const Form = vi.fn(() => <form aria-label="Forbidden form" />);
  renderWithLocale(<AssignmentList assignments={[]} canStart={false} creationForm={<Form />} />);
  expect(Form).not.toHaveBeenCalled();
  expect(screen.getByText("No assignments yet.")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByRole("heading", { name: "Bài tập" })).toBeInTheDocument();
  expect(screen.getByRole("searchbox", { name: "Tìm kiếm bài tập" })).toBeInTheDocument();
  expect(screen.getByText("Chưa có bài tập.")).toBeInTheDocument();
});

it("updates a scheduled badge at its opening timestamp without remounting monitoring", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-01T00:00:00Z"));
  renderWithLocale(<AssignmentStatus archived={false} availableFrom="2026-11-01T00:00:01Z" />);
  expect(screen.getByText("Scheduled")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1001));
  expect(screen.getByText("Active")).toBeInTheDocument();
  expect(api.monitoring).not.toHaveBeenCalled();
});

it("shows only populated date cells and keeps due date distinct from cut-off", () => {
  renderWithLocale(<AssignmentList assignments={[{ ...items[0], due_at: "2026-11-03T00:00:00Z", cutoff_at: "2026-11-04T00:00:00Z" }]} canStart={false} />);
  expect(screen.getByText("Due")).toBeInTheDocument(); expect(screen.getByText("Cut-off")).toBeInTheDocument();
  expect(screen.queryByText("Available")).not.toBeInTheDocument();
  expect(document.querySelectorAll("time")).toHaveLength(2);
});

it("keeps schedule editing usable independently of result visibility and does not reopen after refresh", async () => {
  const props = { assignments: [items[0]], canStart: false, canSchedule: true, onChanged: vi.fn().mockResolvedValue(undefined) };
  api.updateAssignmentSchedule.mockResolvedValue({ ...items[0], policy_revision: 2 });
  const view = renderWithLocale(<AssignmentList {...props} />);
  expect(screen.queryByRole("link", { name: "Results" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("More actions"));
  expect(screen.queryByRole("button", { name: "Monitor submissions" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit schedule" }));
  fireEvent.change(screen.getByLabelText("Maximum starts"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save schedule" }));
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledOnce());
  view.rerender(<AssignmentList {...props} assignments={[{ ...items[0], policy_revision: 2 }]} />);
  expect(screen.queryByRole("button", { name: "Save schedule" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("More actions"));
  fireEvent.click(within(screen.getByRole("article")).getAllByRole("button", { name: "Edit schedule" })[0]);
  expect(screen.getByRole("button", { name: "Save schedule" })).toBeInTheDocument();
});

it("reopens details when the same assignment is requested again from Calendar", async () => {
  const props = { assignments: items, canStart: false, selectedAssignmentId: "one" };
  const view = renderWithLocale(<AssignmentList {...props} selectedAssignmentRequest={1} />);
  await waitFor(() => expect(screen.getByRole("region", { name: "View details · Đề ôn tập" })).toBeInTheDocument());
  // Let the initial external request finish before closing its disclosure.
  await act(async () => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  fireEvent.click(screen.getByRole("button", { name: "Close details" }));
  expect(screen.queryByRole("region", { name: "View details · Đề ôn tập" })).not.toBeInTheDocument();
  view.rerender(<AssignmentList {...props} selectedAssignmentRequest={2} />);
  await screen.findByRole("region", { name: "View details · Đề ôn tập" });
});
