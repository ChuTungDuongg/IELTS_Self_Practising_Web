"use client";

import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { useAssignmentProgress } from "../scheduling/progress-provider";
import { useScheduleText } from "../scheduling/messages";
import { useContentTranslation } from "./content-messages";
import { useAssignmentTargetLabel } from "../assignment-target";

export function ClassworkAssignmentMeta({ assignment }: { assignment: ClassroomAssignment }) {
  const state = useAssignmentProgress(), { st } = useScheduleText(), { ct, locale } = useContentTranslation();
  const targetLabel = useAssignmentTargetLabel();
  const progress = state?.staff ? undefined : state?.items[assignment.id];
  const skills = [...new Set(assignment.version?.modules.map(module => module.module_type) ?? [])];
  const parts: string[] = [assignment.target ? targetLabel(assignment.target, assignment.version).replace(" · ", " / ") : skills.length === 1 ? ct(skills[0]) : ct("assignmentActivity")];
  const historical = assignment.status === "ARCHIVED";
  if (progress) {
    const submission = progress.submission_status;
    if (submission === "SUBMITTED_ON_TIME") parts.push(ct("submitted"));
    else if (submission !== "NOT_STARTED" || !historical) parts.push(st(submission === "NOT_STARTED" && !["OPEN", "ARCHIVED"].includes(progress.availability_status) ? progress.availability_status : submission));
  }
  const due = progress ? progress.effective_due_at : assignment.due_at;
  if (!historical && due && Number.isFinite(Date.parse(due))) {
    parts.push(ct("compactDue", { name: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(new Date(due)) }));
  } else if (!historical && progress?.max_attempts != null && progress.attempts_used > 0 && ["IN_PROGRESS", "NOT_STARTED"].includes(progress.submission_status)) {
    parts.push(ct("compactAttempts", { name: `${progress.attempts_used}/${progress.max_attempts}` }));
  }
  return <p className="classroom-meta classroom-assignment-meta">{parts.slice(0, 3).join(" · ")}</p>;
}

/** One load/error notice for the list, rather than one panel per row. */
export function ClassworkProgressNotice() {
  const state = useAssignmentProgress(), { st } = useScheduleText();
  if (!state || state.staff) return null;
  if (state.error) return <div className="classroom-classwork-progress"><p role="alert">{st("error")}</p><button className="classroom-text-button" type="button" disabled={state.loading} onClick={() => void state.refresh()}>{st("retry")}</button></div>;
  if (state.loading && !Object.keys(state.items).length) return <p className="classroom-meta" role="status">{st("loading")}</p>;
  return null;
}
