import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminClassroomDirectory } from "@/features/admin/classroom-directory";
import AdminClassroomDirectoryPage from "@/app/admin/classrooms/page";
import { getDirectoryClassrooms, getDirectoryPeople, getDirectoryPerson } from "@/lib/api/admin-directory";
import { serverApiRequest } from "@/lib/api/server-client";
import { renderWithLocale } from "./locale-test-utils";

vi.mock("@/lib/api/admin-directory", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/admin-directory")>(),
  getDirectoryClassrooms: vi.fn(), getDirectoryPeople: vi.fn(), getDirectoryPerson: vi.fn(),
}));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));

const teacher = { id: "11111111-1111-4111-8111-111111111111", display_name: "Teacher An", role: "TEACHER" as const, is_active: true, classroom_count: 3 };
const classroom = { id: "22222222-2222-4222-8222-222222222222", name: "Reading Advanced", status: "ARCHIVED" as const, teacher: { id: teacher.id, display_name: teacher.display_name }, enrolled_student_count: 24 };
const people = { items: [teacher], total: 28, offset: 0, limit: 25 };
const classrooms = { items: [classroom], total: 1, offset: 0, limit: 25 };
const filters = { role: "TEACHER" as const, personId: teacher.id, search: "", classroomSearch: "", peopleOffset: 0, classroomOffset: 0 };

describe("admin classroom directory", () => {
  beforeEach(() => {
    window.localStorage.clear(); vi.clearAllMocks();
    vi.mocked(getDirectoryPeople).mockResolvedValue(people);
    vi.mocked(getDirectoryClassrooms).mockResolvedValue(classrooms);
    vi.mocked(getDirectoryPerson).mockResolvedValue(teacher);
  });

  it("keeps teacher and student discovery distinct and opens actual observer and roster screens", () => {
    renderWithLocale(<AdminClassroomDirectory people={people} classrooms={classrooms} selectedPerson={teacher} filters={filters} />);
    expect(screen.getByRole("link", { name: "Teachers" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Students" })).toHaveAttribute("href", "/admin/classrooms?role=USER");
    expect(screen.getByRole("link", { name: "View classroom · Observe" })).toHaveAttribute("href", `/classrooms/${classroom.id}`);
    expect(screen.getByRole("link", { name: "View roster" })).toHaveAttribute("href", `/classrooms/${classroom.id}?tab=people`);
    expect(screen.getByText("24 enrolled students")).toBeInTheDocument();
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /invite|remove|create/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Account administration" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "Back to people directory" })).toHaveAttribute("href", "/admin/classrooms?role=TEACHER");
    expect(screen.getByRole("navigation", { name: "People pages" })).toContainElement(screen.getByRole("link", { name: "Next" }));
  });

  it("localizes observation and search labels while preserving the search draft", () => {
    renderWithLocale(<AdminClassroomDirectory people={people} classrooms={classrooms} selectedPerson={teacher} filters={filters} />);
    const input = screen.getByRole("searchbox", { name: "Search teachers or their classrooms" });
    fireEvent.change(input, { target: { value: "Nguyễn" } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { name: "Danh bạ lớp học" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Tìm giáo viên hoặc lớp phụ trách" })).toBe(input);
    expect(input).toHaveValue("Nguyễn");
    expect(screen.getByRole("link", { name: "Xem lớp · Dự thính" })).toBeInTheDocument();
    expect(screen.getByText("24 học viên đang theo học")).toBeInTheDocument();
  });

  it("loads bounded person and classroom pages with server filters", async () => {
    await AdminClassroomDirectoryPage({ searchParams: Promise.resolve({ role: "TEACHER", person: teacher.id, search: "  An  ", classroomSearch: " Reading ", peopleOffset: "25", classroomOffset: "50" }) });
    expect(getDirectoryPeople).toHaveBeenCalledExactlyOnceWith({ role: "TEACHER", search: "An", offset: 25 }, serverApiRequest);
    expect(getDirectoryClassrooms).toHaveBeenCalledExactlyOnceWith({ teacherId: teacher.id, studentId: undefined, search: "Reading", offset: 50 }, serverApiRequest);
    expect(getDirectoryPerson).toHaveBeenCalledExactlyOnceWith(teacher.id, "TEACHER", serverApiRequest);
  });

  it("uses the student enrollment filter and rejects malformed pagination and person IDs locally", async () => {
    await AdminClassroomDirectoryPage({ searchParams: Promise.resolve({ role: "USER", person: teacher.id, peopleOffset: "-1", classroomOffset: "NaN" }) });
    expect(getDirectoryClassrooms).toHaveBeenCalledWith({ teacherId: undefined, studentId: teacher.id, search: "", offset: 0 }, serverApiRequest);
    expect(getDirectoryPeople).toHaveBeenCalledWith({ role: "USER", search: "", offset: 0 }, serverApiRequest);
    vi.clearAllMocks();
    await AdminClassroomDirectoryPage({ searchParams: Promise.resolve({ role: "ADMIN", person: "broken" }) });
    expect(getDirectoryPerson).not.toHaveBeenCalled();
    expect(getDirectoryPeople).toHaveBeenCalledWith({ role: "TEACHER", search: "", offset: 0 }, serverApiRequest);
  });

  it("normalizes repeated URL parameters before requesting bounded server pages", async () => {
    await AdminClassroomDirectoryPage({ searchParams: Promise.resolve({ role: ["USER", "TEACHER"], search: ["  Minh  ", "ignored"], peopleOffset: ["25", "50"] }) });
    expect(getDirectoryPeople).toHaveBeenCalledExactlyOnceWith({ role: "USER", search: "Minh", offset: 25 }, serverApiRequest);
  });
});
