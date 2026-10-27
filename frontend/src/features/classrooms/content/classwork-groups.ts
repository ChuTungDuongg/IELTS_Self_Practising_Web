import type { Classwork, ClassworkItem, ClassroomResource, ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { ordered } from "./classwork-order";

export type ClassworkRow = { key: string; item?: ClassworkItem; resource?: ClassroomResource; assignment?: ClassroomAssignment };
export type ClassworkGroup = { key: string; kind: "topic" | "unplaced" | "archivedAssignments" | "archivedResources"; section: ClassroomSection | null; rows: ClassworkRow[] };

/** Presentation only. API responses remain the authority for access and lifecycle. */
export function classworkGroups(data: Classwork, assignments: ClassroomAssignment[], canInspect: boolean): ClassworkGroup[] {
  const topics: ClassworkGroup[] = ordered(data.sections).filter(section => canInspect || section.status === "PUBLISHED").map(section => ({ key: `section-${section.id}`, kind: "topic", section, rows: [] }));
  const unplaced: ClassworkGroup = { key: "section-uncategorized", kind: "unplaced", section: null, rows: [] };
  const archived: ClassworkGroup = { key: "archived-assignments", kind: "archivedAssignments", section: null, rows: [] };
  const resources: ClassworkGroup = { key: "archived-resources", kind: "archivedResources", section: null, rows: [] };
  const topicById = new Map(topics.map(group => [group.section!.id, group]));
  const visibleAssignments = assignments.filter(assignment => !(data.removed_assignment_ids ? data.removed_assignment_ids.includes(assignment.id) : assignment.classwork_hidden));
  const assignmentById = new Map(visibleAssignments.map(assignment => [assignment.id, assignment]));
  const resourceById = new Map(data.resources.map(resource => [resource.id, resource]));
  const seen = new Set<string>();
  function add(row: ClassworkRow, target: ClassworkGroup) {
    if (seen.has(row.key)) return;
    seen.add(row.key); target.rows.push(row);
  }
  for (const item of ordered(data.items)) {
    const target = item.section_id ? topicById.get(item.section_id) : unplaced;
    const assignment = item.assignment_id ? assignmentById.get(item.assignment_id) : undefined;
    const resource = item.resource_id ? resourceById.get(item.resource_id) : undefined;
    if (assignment) {
      if (assignment.status === "ARCHIVED") add({ key: `assignment-${assignment.id}`, assignment, item }, archived);
      else if (target) add({ key: `assignment-${assignment.id}`, assignment, item }, target);
    } else if (resource && target && (canInspect || resource.status === "PUBLISHED")) {
      add({ key: `resource-${resource.id}`, resource, item }, resource.status === "ARCHIVED" ? resources : target);
    }
  }
  // Canonical assignments may have no placement, including retained student history.
  for (const assignment of visibleAssignments) add({ key: `assignment-${assignment.id}`, assignment }, assignment.status === "ARCHIVED" ? archived : unplaced);
  return [...topics, ...[unplaced, archived, resources].filter(group => group.rows.length)];
}
