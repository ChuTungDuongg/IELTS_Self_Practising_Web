"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AnalyticsIcon, BuilderIcon, HeadphonesIcon, LibraryIcon, ReadingIcon } from "@/components/ui/icons";
import { archiveAssignment, type ClassroomAssignment } from "@/lib/api/classrooms";
import { AssignmentTargetSummary } from "../assignment-target";
import { ArchivedAssignmentActions } from "../content/archived-assignment-actions";
import { ContentAction } from "../content/content-action";
import { useContentTranslation } from "../content/content-messages";
import { ActionMenu } from "../lms/action-menu";
import { AssignmentManagement } from "../scheduling/assignment-management";
import { ProgressSummary } from "../scheduling/progress-summary";
import { useScheduleText } from "../scheduling/messages";
import { StartAssignment } from "./start-assignment";
import { useAssignmentsText } from "./messages";
import { AssignmentStatus } from "./assignment-status";

export type AssignmentRowPermissions = { canViewResults: boolean; canStart: boolean; canSchedule: boolean; canArchive: boolean; archived: boolean; resultNamespace: "teacher" | "shared"; onChanged?: () => Promise<unknown> };
function SpeakingIcon() { return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M6 10v2a6 6 0 0 0 12 0v-2M12 18v4M8 22h8" /></svg>; }
function AssignmentDates({ assignment }: { assignment: ClassroomAssignment }) {
  const { at } = useAssignmentsText(), { date } = useScheduleText();
  const entries = assignment.status === "ARCHIVED" ? [["archivedOn", assignment.archived_at] as const] : [["available", assignment.available_from], ["due", assignment.due_at], ["cutoff", assignment.cutoff_at]] as const;
  const valid = entries.filter(([, value]) => value && Number.isFinite(Date.parse(value)));
  return valid.length ? <dl className="assignments-dates">{valid.map(([label, value]) => <div key={label}><dt>{at(label)}</dt><dd><time dateTime={value!}>{date(value)}</time></dd></div>)}</dl> : assignment.status !== "ARCHIVED" ? <p className="assignments-no-dates">{at("noDates")}</p> : null;
}

export function AssignmentRow({ assignment, focused = false, focusRequest = 0, ...permissions }: { assignment: ClassroomAssignment; focused?: boolean; focusRequest?: number } & AssignmentRowPermissions) {
  const { at } = useAssignmentsText(), { ct } = useContentTranslation(), { st } = useScheduleText();
  const [details, setDetails] = useState(focused), [edit, setEdit] = useState(false);
  const [detailRequest, setDetailRequest] = useState(0);
  useEffect(() => {
    if (!focused) return;
    const frame = requestAnimationFrame(() => setDetails(true));
    return () => cancelAnimationFrame(frame);
  }, [focused, focusRequest]);
  const history = assignment.status === "ARCHIVED";
  const title = assignment.title ?? assignment.version?.test_title ?? at("title");
  const skill = assignment.target?.mode === "FULL_MOCK" ? "FULL_MOCK" : assignment.target?.module;
  const Icon = skill === "LISTENING" ? HeadphonesIcon : skill === "WRITING" ? BuilderIcon : skill === "SPEAKING" ? SpeakingIcon : skill === "FULL_MOCK" ? LibraryIcon : ReadingIcon;
  const canChange = !permissions.archived && permissions.canSchedule;
  function showDetails(editing = false) { setEdit(editing); setDetailRequest(value => value + 1); setDetails(true); }
  return <article id={`assignment-${assignment.id}`} tabIndex={-1} className={`assignments-row${history ? " assignments-row-archived" : ""}`}>
    <div className="assignments-row-main">
      <div className="assignments-identity"><span className="assignments-skill-icon" data-skill={skill ?? "LEGACY"}><Icon /></span><div>
        <h4><button type="button" aria-expanded={details} aria-controls={`assignment-details-${assignment.id}`} onClick={() => { setDetails(value => !value); setEdit(false); }}>{title}</button></h4>
        {assignment.target ? <AssignmentTargetSummary assignment={assignment} /> : <p className="classroom-meta">{at("flexible")}</p>}
        <AssignmentStatus archived={history} availableFrom={assignment.available_from} />
      </div></div>
      <AssignmentDates assignment={assignment} />
      <div className="assignments-row-actions">
        {history ? canChange && permissions.onChanged ? <ArchivedAssignmentActions assignment={assignment} onChanged={permissions.onChanged} onDetails={() => showDetails()} /> : <button type="button" className="btn btn-secondary" onClick={() => showDetails()}>{at("details")}</button> : <>
          {permissions.canViewResults ? <Link className="btn btn-secondary" href={`${permissions.resultNamespace === "shared" ? "" : "/teacher"}/classrooms/${assignment.classroom_id}/assignments/${assignment.id}/results`}><AnalyticsIcon />{at("results")}</Link> : null}
          {canChange || permissions.canArchive && !permissions.archived ? <ActionMenu label={at("more")}>
            {permissions.canViewResults ? <button type="button" onClick={() => showDetails()}>{st("monitor")}</button> : null}
            {canChange ? <button type="button" onClick={() => showDetails(true)}>{st("edit")}</button> : null}
            {permissions.canArchive ? <ContentAction action={() => archiveAssignment(assignment.classroom_id, assignment.id)} onDone={permissions.onChanged} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction> : null}
          </ActionMenu> : null}
        </>}
      </div>
    </div>
    {permissions.canStart ? <div className="assignments-student-progress"><ProgressSummary assignmentId={assignment.id} actions />{!history && !permissions.archived ? <StartAssignment assignment={assignment} /> : null}</div> : null}
    {details ? <section className="assignments-details" id={`assignment-details-${assignment.id}`} aria-label={`${at("details")} · ${title}`}>
      <div className="classroom-section-heading"><h5>{at("details")}</h5><button type="button" className="classroom-text-button" onClick={() => setDetails(false)}>{at("close")}</button></div>
      {assignment.note ? <p className="assignments-instructions">{assignment.note}</p> : null}
      {permissions.canSchedule && !assignment.target ? <p className="classroom-meta">{ct("legacyTarget")}</p> : null}
      {permissions.canViewResults || canChange && !history ? <>
        {history && permissions.canViewResults ? <Link className="btn btn-secondary" href={`${permissions.resultNamespace === "shared" ? "" : "/teacher"}/classrooms/${assignment.classroom_id}/assignments/${assignment.id}/results`}>{at("results")}</Link> : null}
        <AssignmentManagement key={`${assignment.id}-${detailRequest}`} assignment={assignment} initialEditing={edit} canEdit={canChange && !history} canMonitor={permissions.canViewResults} shared={permissions.resultNamespace === "shared"} onChanged={permissions.onChanged} />
      </> : null}
    </section> : null}
  </article>;
}
