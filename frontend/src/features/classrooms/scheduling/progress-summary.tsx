"use client";
import Link from "next/link";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import type { AssignmentProgress } from "@/lib/api/assignment-scheduling";
import { useAssignmentProgress, ProgressLoadState } from "./progress-provider";
import { useScheduleText } from "./messages";

export function ScheduleSummary({ assignment }: { assignment: ClassroomAssignment }) {
  const { st, date } = useScheduleText();
  return <dl className="assignment-policy-summary"><div><dt>{st("available")}</dt><dd>{date(assignment.available_from)}</dd></div><div><dt>{st("due")}</dt><dd>{date(assignment.due_at)}</dd></div><div><dt>{st("cutoff")}</dt><dd>{date(assignment.cutoff_at)}</dd></div></dl>;
}
export function ProgressSummary({ assignmentId, value, actions = false }: { assignmentId: string; value?: AssignmentProgress; actions?: boolean }) {
  const state = useAssignmentProgress(), { st, date } = useScheduleText();
  if (state?.staff && !value) { const assignment = state.assignments.find(item => item.id === assignmentId); return assignment ? <ScheduleSummary assignment={assignment} /> : null; }
  const progress = value ?? state?.items[assignmentId];
  if (!progress) return state ? <ProgressLoadState /> : null;
  const resume = progress.resume_session_id ? `/test-session/${progress.resume_session_id}` : progress.resume_attempt_id ? `/attempt/${progress.resume_attempt_id}` : null;
  return <div className="assignment-progress-summary"><p><strong>{st(progress.submission_status)}</strong> · {st(progress.availability_status)}</p><p className="classroom-meta">{st("attempts")}: {progress.attempts_used} / {progress.max_attempts ?? st("unlimited")}{progress.attempts_remaining !== null ? ` · ${st("remaining")}: ${progress.attempts_remaining}` : ""}</p>
    <dl className="assignment-policy-summary"><div><dt>{st("due")}</dt><dd>{date(progress.effective_due_at)}</dd></div><div><dt>{st("cutoff")}</dt><dd>{date(progress.effective_cutoff_at)}</dd></div>{progress.completed_at ? <div><dt>{st("completed")}</dt><dd>{date(progress.completed_at)}</dd></div> : null}</dl>
    {progress.completed_at ? <p className="classroom-meta">{st(progress.accepted ? "accepted" : "notAccepted")}</p> : null}
    {!progress.can_start && progress.start_blocked_reason ? <p className="classroom-meta">{st(progress.start_blocked_reason)}</p> : null}
    {actions && state ? <button className="classroom-text-button" type="button" disabled={state.loading} onClick={() => void state.refresh()}>{st("refresh")}</button> : null}
    {actions ? <div className="classroom-toolbar">{progress.can_resume && resume ? <Link className="btn btn-secondary" href={resume}>{st("continue")}</Link> : null}{progress.result_attempt_id ? <Link className="btn btn-secondary" href={`/review/${progress.result_attempt_id}`}>{st("result")}</Link> : null}</div> : null}
  </div>;
}
