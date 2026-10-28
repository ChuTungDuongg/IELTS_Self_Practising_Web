import { screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ClassroomOverview } from "@/features/classrooms/overview/classroom-overview";
import { classroomPermissions } from "@/features/classrooms/classroom-permissions";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { renderWithLocale } from "./locale-test-utils";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
const room = { id: "room", teacher_id: "owner", teacher_name: "Teacher", name: "Class", description: "Study together", active_member_count: 1, status: "ACTIVE" as const, archived_at: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
const assignment = (id: string, status: "ACTIVE" | "ARCHIVED") => ({ id, status, title: id, target: { mode: "MODULE", module: "READING" } }) as ClassroomAssignment;
const calendar = { total: 2, items: [{ assignment_id: "active", title: "Effective deadline", kind: "DUE" as const, at: "2030-01-01T00:00:00Z", progress: null }, { assignment_id: "archived", title: "Archived deadline", kind: "DUE" as const, at: "2030-01-02T00:00:00Z", progress: null }] };
const base = { classroom: room, directory: "/classrooms", workspace: "/classrooms/room", assignments: [assignment("active", "ACTIVE"), assignment("archived", "ARCHIVED")], posts: [], calendar, dashboard: null };

it("uses the effective calendar deadline and excludes archived assignments", () => {
  renderWithLocale(<ClassroomOverview {...base} permissions={classroomPermissions(room, { id: "student", role: "STUDENT" })} />);
  expect(screen.getByRole("link", { name: /Effective deadline/ })).toHaveAttribute("href", "/classrooms/room?assignment=active");
  expect(screen.queryByText("Archived deadline")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Enter classroom" })).toHaveAttribute("href", "/classrooms/room");
  expect(screen.queryByText("Edit classroom")).not.toBeInTheDocument();
  expect(within(screen.getByLabelText("Class overview")).getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Data unavailable")).toHaveLength(4);
});

it("keeps observers read-only and links canonical feed activities", () => {
  const post = { id: "resource", kind: "RESOURCE_ACTIVITY" as const, title: "Shared notes", body: "", status: "PUBLISHED" as const, pinned: false, locked: false, author_id: "owner", author_name: "Teacher", author_role: "TEACHER", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", published_at: "2026-01-01T00:00:00Z", comment_count: 0, resource_ids: [], assignment_id: null };
  renderWithLocale(<ClassroomOverview {...base} posts={[post]} permissions={classroomPermissions(room, { id: "admin", role: "ADMIN" })} />);
  expect(screen.getByText("Read only")).toBeInTheDocument();
  expect(screen.queryByText("Edit classroom")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Shared notes/ })).toHaveAttribute("href", "/classrooms/room#classwork-resource-resource");
  expect(screen.getByRole("link", { name: "View classroom" })).toHaveAttribute("href", "/classrooms/room");
});

it("renders an authorized roster preview without private email details", () => {
  renderWithLocale(<ClassroomOverview {...base} members={[{ user_id: "student", display_name: "Example Student" }]} permissions={classroomPermissions({ ...room, capabilities: ["roster.view"] }, { id: "admin", role: "ADMIN" })} />);
  expect(screen.getByText("Example Student")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Class members" }).closest("section")).toContainElement(screen.getByText("Example Student"));
});
