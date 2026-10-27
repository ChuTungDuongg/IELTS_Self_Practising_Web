"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getClasswork, type Classwork } from "@/lib/api/classroom-content";
import type { Classroom, ClassroomAssignment } from "@/lib/api/classrooms";
import { AssignmentList } from "../assignment-list";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { ClassroomStream } from "./classroom-stream";
import { ClassworkPanel } from "./classwork-panel";
import { ClassroomHeader } from "../lms/classroom-header";
import { GradebookPanel } from "../lms/gradebook";
import { useLmsText } from "../lms/messages";
import "./classroom-workspace.css";
import "../scheduling/scheduling.css";
import "../lms/lms.css";
import { AssignmentProgressProvider } from "../scheduling/progress-provider";
import { AssignmentCalendarPanel } from "../scheduling/assignment-calendar";
import { useScheduleText } from "../scheduling/messages";
import { LearningAnalyticsPanel } from "../lms/learning-analytics";
import { LearningPlansPanel } from "../lms/learning-plans";
import { AcademicProfilePanel } from "../lms/student-profile";

type Tab = "stream" | "classwork" | "assignments" | "calendar" | "people" | "gradebook" | "analytics" | "myProgress";
type WorkspaceProps = {
  classroom: Classroom; user: { id: string; role: string }; assignments: ClassroomAssignment[];
  people?: ReactNode; assignmentForm?: ReactNode; management?: ReactNode; canManage: boolean;
  selectedPostId?: string | null; selectedAssignmentId?: string | null;
};
export function ClassroomWorkspace(props: WorkspaceProps) {
  return <AssignmentProgressProvider classroomId={props.classroom.id} ids={props.assignments.map(item => item.id)} assignments={props.assignments} staff={props.canManage}><ClassroomWorkspaceContent {...props} /></AssignmentProgressProvider>;
}
function ClassroomWorkspaceContent({ classroom, user, assignments, people, assignmentForm, management, canManage, selectedPostId = null, selectedAssignmentId = null }: WorkspaceProps) {
  const { ct } = useContentTranslation(), { st } = useScheduleText(), { lt } = useLmsText();
  const [tab, setTab] = useState<Tab>(selectedAssignmentId ? "assignments" : "stream");
  const [data, setData] = useState<Classwork | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null);
  const [assignmentFocus, setAssignmentFocus] = useState<string | null>(selectedAssignmentId), [creating, setCreating] = useState(false);
  const [createAction, setCreateAction] = useState<"section" | "resource" | "post" | null>(null), [actionSequence, setActionSequence] = useState(0), [student, setStudent] = useState<string | null>(null);
  const canOwn = user.role === "TEACHER" && user.id === classroom.teacher_id, archived = classroom.status === "ARCHIVED";
  const canAuthor = (classroom.capabilities?.includes("content.manage") ?? canOwn) && !archived;
  const canSchedule = (classroom.capabilities?.includes("assignments.manage") ?? canOwn) && user.role !== "ADMIN";
  const canModerate = (classroom.capabilities?.includes("discussion.moderate") ?? canOwn) && !archived;
  const canAnalytics = classroom.capabilities?.includes("analytics.view") ?? canOwn;
  const canPlans = (classroom.capabilities?.includes("learning_plans.manage") ?? canOwn) && !archived;
  const requestId = useRef(0);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const sequence = ++requestId.current; setLoading(true); setError(null);
    try { const next = await getClasswork(classroom.id, undefined, signal); if (sequence === requestId.current && !signal?.aborted) setData(next); }
    catch (caught) { if (sequence === requestId.current && !signal?.aborted) setError(contentError(caught, ct("error"))); throw caught; }
    finally { if (sequence === requestId.current && !signal?.aborted) setLoading(false); }
  }, [classroom.id, ct]);
  useEffect(() => { const controller = new AbortController(); void Promise.resolve().then(() => { if (!controller.signal.aborted) void refresh(controller.signal).catch(() => {}); }); return () => controller.abort(); }, [refresh]);
  useEffect(() => {
    function navigateContent() { if (!selectedAssignmentId && /^#(?:section-|assignment-|resource-|classwork-|item-)/.test(window.location.hash)) setTab("classwork"); }
    navigateContent(); window.addEventListener("hashchange", navigateContent);
    return () => window.removeEventListener("hashchange", navigateContent);
  }, [selectedAssignmentId]);
  useEffect(() => {
    if (tab !== "assignments" || !assignmentFocus) return;
    const element = document.getElementById(`assignment-${assignmentFocus}`); element?.scrollIntoView?.({ block: "nearest" }); element?.focus();
  }, [tab, assignmentFocus]);
  function openAssignment(id: string) { setAssignmentFocus(id); setCreateAction(null); setTab("assignments"); }
  function createContent(kind: "section" | "resource" | "post") { setCreateAction(kind); setActionSequence(value => value + 1); setTab(kind === "post" ? "stream" : "classwork"); }
  function createAssignment() { setTab("assignments"); setCreating(true); }
  const contentActions = canAuthor ? [{ label: lt("announce"), action: () => createContent("post") }, { label: ct("addSection"), action: () => createContent("section") }, { label: ct("addResource"), action: () => createContent("resource") }] : [];
  const tabs: Tab[] = ["stream", "classwork", "assignments", "calendar", ...(canManage ? ["people" as const, "gradebook" as const] : []), ...(canAnalytics ? ["analytics" as const] : []), "myProgress"];
  return <div className="classroom-workspace" data-ui>
    <ClassroomHeader classroom={classroom} management={management} onManage={canManage ? () => setTab("people") : undefined} canCreate={!!assignmentForm && !archived} contentActions={contentActions} onCreate={createAssignment} />
    {archived ? <p className="notice" role="status">{ct("archivedRoom")}</p> : user.role === "ADMIN" ? <p className="classroom-meta">{ct("readOnly")}</p> : null}
    <div className="classroom-tabs" role="tablist" aria-label={classroom.name} onKeyDown={event => {
      const index = tabs.indexOf(tab); const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); setTab(tabs[next]); document.getElementById(`classroom-tab-${tabs[next]}`)?.focus(); }
    }}>{tabs.map(key => <button key={key} id={`classroom-tab-${key}`} type="button" role="tab" aria-selected={tab === key} aria-controls={`classroom-panel-${key}`} tabIndex={tab === key ? 0 : -1} onClick={() => { setTab(key); setCreateAction(null); setStudent(null); }}>{key === "gradebook" || key === "analytics" || key === "myProgress" ? lt(key) : key === "calendar" ? st("calendar") : ct(key)}</button>)}</div>
    <div className="classroom-columns">
      {tabs.map(panelTab => <div key={panelTab} hidden={tab !== panelTab} className="classroom-main" id={`classroom-panel-${panelTab}`} role="tabpanel" aria-labelledby={`classroom-tab-${panelTab}`} tabIndex={0}>
        {tab === panelTab ? <>
        {tab === "stream" && canManage ? <section className="classroom-overview" aria-label={lt("overview")}><div><strong>{assignments.filter(item => item.status === "ACTIVE").length}</strong><span>{lt("activeAssignments")}</span></div><div><strong>{classroom.active_member_count ?? "—"}</strong><span>{lt("students")}</span></div><div className="classroom-toolbar">{canAuthor ? <button type="button" className="btn btn-secondary" onClick={() => setTab("classwork")}>{lt("materials")}</button> : null}{people ? <button type="button" className="btn btn-secondary" onClick={() => setTab("people")}>{ct("people")}</button> : null}<button type="button" className="btn btn-secondary" onClick={() => setTab("gradebook")}>{lt("gradebook")}</button></div></section> : null}
        {tab === "stream" ? <ClassroomStream key={`stream-${createAction === "post" ? actionSequence : 0}`} initialCompose={createAction === "post"} classroomId={classroom.id} resources={data?.resources ?? []} userId={user.id} canAuthor={canAuthor} canModerate={canModerate} canInspect={canManage} archived={archived} admin={user.role === "ADMIN"} onOpenAssignment={openAssignment} selectedPostId={selectedPostId} /> : null}
        {tab === "classwork" ? <>{loading && !data ? <div className="classroom-panel classroom-skeleton" role="status"><h2>{ct("classwork")}</h2><p>{ct("loading")}</p><div /><div /></div> : null}{error ? <div className="classroom-panel"><p role="alert" className="notice notice-error">{error}</p><button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void refresh().catch(() => {})}>{ct("retry")}</button></div> : null}{data ? <ClassworkPanel key={`work-${actionSequence}`} initialAction={createAction === "section" || createAction === "resource" ? createAction : undefined} onCreateAssignment={assignmentForm ? createAssignment : undefined} classroomId={classroom.id} data={data} assignments={assignments} canAuthor={canAuthor} canInspect={canManage} onRefresh={refresh} onChange={setData} onOpenAssignment={openAssignment} /> : null}</> : null}
        {tab === "assignments" ? <div className="classroom-assignments">{assignmentForm && !archived ? <section className="classroom-create-assignment"><button type="button" className="btn btn-primary" aria-expanded={creating} onClick={() => setCreating(value => !value)}>{creating ? lt("close") : lt("newAssignment")}</button>{creating ? <div className="classroom-focused-form">{assignmentForm}</div> : null}</section> : null}<AssignmentList assignments={assignments} canManage={canManage} canSchedule={canSchedule} canArchive={canSchedule || user.role === "ADMIN"} archived={archived} resultNamespace={user.role === "TEACHER" ? "teacher" : "shared"} /></div> : null}
        {tab === "calendar" ? <AssignmentCalendarPanel classroomId={classroom.id} onOpenAssignment={openAssignment} /> : null}
        {tab === "people" && canManage ? <section aria-label={ct("people")}><h2 className="section-title mb-3">{ct("people")}</h2>{people ?? <p className="classroom-empty">{ct("emptyPeople")}</p>}</section> : null}
        {tab === "gradebook" && canManage ? <GradebookPanel classroomId={classroom.id} assignments={assignments} canEdit={!archived && canSchedule} canAnalytics={canAnalytics} canPlans={canPlans} classwork={data} archived={archived} onOpenAssignment={openAssignment} /> : null}
        {tab === "analytics" && canAnalytics ? student ? <AcademicProfilePanel classroomId={classroom.id} studentId={student} canAnalytics canPlans={canPlans} classwork={data} assignments={assignments} archived={archived} onOpenAssignment={openAssignment} onClose={() => setStudent(null)} /> : <LearningAnalyticsPanel classroomId={classroom.id} onOpenAssignment={openAssignment} onStudent={setStudent} /> : null}
        {tab === "myProgress" ? <><LearningAnalyticsPanel classroomId={classroom.id} own onOpenAssignment={openAssignment} /><LearningPlansPanel classroomId={classroom.id} studentId={user.id} own classwork={data} assignments={assignments} archived={archived} onOpenAssignment={openAssignment} /></> : null}
        </> : null}
      </div>)}
    </div>
  </div>;
}
