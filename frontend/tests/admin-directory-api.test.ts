import { describe, expect, it, vi } from "vitest";
import { getDirectoryClassrooms, getDirectoryPeople, getDirectoryPerson } from "@/lib/api/admin-directory";

const emptyPage = { items: [], total: 0, offset: 0, limit: 25 };

describe("admin observation directory client", () => {
  it("requests only a bounded page of the selected role with server search", async () => {
    const request = vi.fn().mockResolvedValue(emptyPage);
    await getDirectoryPeople({ role: "USER", search: "  Minh + An  ", offset: 25 }, request);
    expect(request).toHaveBeenCalledExactlyOnceWith("/admin/directory/people?role=USER&search=Minh%20%2B%20An&offset=25&limit=25");
  });

  it("sends ownership and enrollment filters to the server", async () => {
    const request = vi.fn().mockResolvedValue(emptyPage);
    await getDirectoryClassrooms({ teacherId: "teacher-1", studentId: "student-1", search: "Reading", offset: 50 }, request);
    expect(request).toHaveBeenCalledExactlyOnceWith("/admin/directory/classrooms?teacher_id=teacher-1&student_id=student-1&search=Reading&offset=50&limit=25");
  });

  it("validates minimal directory identity without copying private profile fields", async () => {
    const person = { id: "person-1", display_name: "Minh", role: "USER", is_active: true, classroom_count: 2 };
    const request = vi.fn().mockResolvedValue({ ...person, email: "private@example.com", phone_number: "private" });
    expect(await getDirectoryPerson("person/1", "USER", request)).toEqual(person);
    expect(request).toHaveBeenCalledExactlyOnceWith("/admin/directory/people/person%2F1?role=USER");
  });
});
