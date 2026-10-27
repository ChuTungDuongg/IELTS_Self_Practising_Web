import { notFound } from "next/navigation";
import { z } from "zod";
import { AdminClassroomDirectory } from "@/features/admin/classroom-directory";
import { getDirectoryClassrooms, getDirectoryPeople, getDirectoryPerson } from "@/lib/api/admin-directory";
import { ApiError } from "@/lib/api/client";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

type SearchParams = {
  role?: string | string[]; person?: string | string[]; search?: string | string[]; classroomSearch?: string | string[];
  peopleOffset?: string | string[]; classroomOffset?: string | string[];
};

function scalar(value?: string | string[]): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function offset(value?: string | string[]): number {
  const parsed = Number(scalar(value) ?? 0);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
}

export default async function AdminClassroomDirectoryPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const role = scalar(params.role) === "USER" ? "USER" as const : "TEACHER" as const;
  const parsedPersonId = z.uuid().safeParse(scalar(params.person));
  const personId = parsedPersonId.success ? parsedPersonId.data : undefined;
  const search = scalar(params.search)?.trim().slice(0, 160) ?? "";
  const classroomSearch = scalar(params.classroomSearch)?.trim().slice(0, 160) ?? "";
  const peopleOffset = offset(params.peopleOffset);
  const classroomOffset = offset(params.classroomOffset);
  const [people, classrooms, selectedPerson] = await Promise.all([
    getDirectoryPeople({ role, search, offset: peopleOffset }, serverApiRequest),
    getDirectoryClassrooms({ teacherId: role === "TEACHER" ? personId : undefined, studentId: role === "USER" ? personId : undefined, search: classroomSearch, offset: classroomOffset }, serverApiRequest),
    personId ? getDirectoryPerson(personId, role, serverApiRequest).catch(error => {
      if (error instanceof ApiError && error.code === "USER_NOT_FOUND") notFound();
      throw error;
    }) : null,
  ]);
  return <AdminClassroomDirectory key={`${role}:${personId ?? ""}:${search}:${classroomSearch}`} people={people} classrooms={classrooms} selectedPerson={selectedPerson} filters={{ role, personId, search, classroomSearch, peopleOffset, classroomOffset }} />;
}
