"use client";

import type { AssignmentTarget, ClassroomAssignment } from "@/lib/api/classrooms";
import type { VersionDetail } from "@/lib/api/schema";
import { useContentTranslation } from "./content/content-messages";
import { useAssignmentProgress } from "./scheduling/progress-provider";

export function assignmentUnits(module?: VersionDetail["modules"][number]) {
  if (!module) return [];
  if (module.module_type === "READING") return (module.reading_passages ?? []).map(unit => ({ id: unit.id, kind: "READING_PASSAGE" as const, number: unit.order_index + 1 }));
  if (module.module_type === "LISTENING") return (module.listening_sections ?? []).map(unit => ({ id: unit.id, kind: "LISTENING_PART" as const, number: unit.order_index + 1 }));
  if (module.module_type === "WRITING") return (module.writing_tasks ?? []).map(unit => ({ id: unit.id, kind: "WRITING_TASK" as const, number: unit.task_number }));
  return (module.speaking_parts ?? []).flatMap(part => part.prompts.map(unit => ({ id: unit.id, kind: "SPEAKING_PROMPT" as const, number: unit.order_index + 1, partNumber: part.part_number })));
}

export function useAssignmentTargetLabel() {
  const { ct } = useContentTranslation();
  function label(target: AssignmentTarget, version?: VersionDetail | null) {
    if (target.mode === "FULL_MOCK") return ct("fullMockTarget");
    const skill = target.module ? ct(target.module) : ct("assignmentActivity");
    if (target.scope !== "FOCUSED_UNIT" || !target.focused_unit) return skill + " · " + ct("fullModuleTarget");
    const unit = assignmentUnits(version?.modules.find(module => module.module_type === target.module)).find(unit => unit.id === target.focused_unit?.id);
    const part = unit && "partNumber" in unit ? ct("speakingPartTarget", { name: String(unit.partNumber) }) + " / " : "";
    return skill + " · " + part + ct(target.focused_unit.kind, { name: unit ? String(unit.number) : "" });
  }
  return label;
}

export function AssignmentTargetSummary({ assignment }: { assignment: ClassroomAssignment }) {
  const label = useAssignmentTargetLabel();
  return assignment.target ? <p className="classroom-meta">{label(assignment.target, assignment.version)}</p> : null;
}

export function AssignmentActivityTarget({ assignmentId, target }: { assignmentId: string; target?: AssignmentTarget | null }) {
  const state = useAssignmentProgress(), label = useAssignmentTargetLabel();
  const assignment = state?.assignments.find(assignment => assignment.id === assignmentId);
  const selected = target ?? assignment?.target;
  return selected ? <span className="classroom-meta classroom-assignment-target">{label(selected, assignment?.version)}</span> : null;
}
