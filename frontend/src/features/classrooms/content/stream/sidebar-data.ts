import type { Classwork } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import type { AssignmentProgress } from "@/lib/api/assignment-scheduling";

export function upcomingAssignments(assignments: ClassroomAssignment[], progress: Record<string, AssignmentProgress>, student: boolean, now: number) {
  return assignments.flatMap(assignment => {
    const own = student ? progress[assignment.id] : undefined;
    if (assignment.status !== "ACTIVE" || student && (!own || own.completed_at || own.availability_status === "ARCHIVED" || own.availability_status === "CLOSED")) return [];
    const due = own ? own.effective_due_at : assignment.due_at;
    const cutoff = own ? own.effective_cutoff_at : assignment.cutoff_at;
    const date = due && Date.parse(due) > now ? due : cutoff && Date.parse(cutoff) > now ? cutoff : null;
    return date ? [{ assignment, date, kind: date === due ? "due" as const : "cutoff" as const }] : [];
  }).sort((a, b) => Date.parse(a.date) - Date.parse(b.date) || a.assignment.id.localeCompare(b.assignment.id));
}

export function sharedResourceCount(data: Classwork) {
  const visibleTopics = new Set(data.sections.filter(item => item.status === "PUBLISHED").map(item => item.id));
  const shared = new Set(data.items.filter(item => item.resource_id && (!item.section_id || visibleTopics.has(item.section_id))).map(item => item.resource_id));
  return data.resources.filter(item => item.status === "PUBLISHED" && shared.has(item.id)).length;
}
