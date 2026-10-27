"use client";
import { useSyncExternalStore, type ReactNode } from "react";
import type { Classwork, ClassroomPost } from "@/lib/api/classroom-content";
import type { Classroom, ClassroomAssignment } from "@/lib/api/classrooms";
import { AssignmentTargetSummary } from "../../assignment-target";
import { useAssignmentProgress } from "../../scheduling/progress-provider";
import { useContentTranslation } from "../content-messages";
import { StreamAvatar, StreamGlyph, StreamTime } from "./identity";
import { useStreamText } from "./messages";
import { sharedResourceCount, upcomingAssignments } from "./sidebar-data";

export type StreamRosterMember = { user_id: string; display_name: string };
export type StreamNavigation = (tab: "people" | "classwork" | "calendar" | "assignments") => void;
function subscribeClock(notify: () => void) {
  let timer: number;
  function update() { window.clearTimeout(timer); notify(); timer = window.setTimeout(update, 60_000 - Date.now() % 60_000 + 1); }
  update(); document.addEventListener("visibilitychange", update);
  return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", update); };
}
const snapshot = () => Math.floor(Date.now() / 60_000) * 60_000;
const serverSnapshot = () => null;
function SidebarSection({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return <section className="stream-sidebar-card" aria-label={title}><header><h3>{title}</h3>{action}</header>{children}</section>;
}
export function StreamSidebar({ classroom, assignments, classwork, contentError, members, canViewRoster, student, posts, onNavigate, onOpenAssignment, onShowFeed }: { classroom: Classroom; assignments: ClassroomAssignment[]; classwork?: Classwork | null; contentError?: boolean; members?: StreamRosterMember[]; canViewRoster: boolean; student: boolean; posts: ClassroomPost[]; onNavigate: StreamNavigation; onOpenAssignment: (id: string) => void; onShowFeed?: () => void }) {
  const { tt } = useStreamText(), { ct } = useContentTranslation(), progress = useAssignmentProgress();
  const now = useSyncExternalStore(subscribeClock, snapshot, serverSnapshot);
  const deadlinesReady = now !== null && (!student || !!progress && !progress.loading && !progress.error);
  const upcoming = deadlinesReady ? upcomingAssignments(assignments, progress?.items ?? {}, student, now) : [];
  const recent = [...posts].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 3);
  const all = (tab: Parameters<StreamNavigation>[0], label = tt("viewAll")) => <button type="button" className="stream-sidebar-link" onClick={() => onNavigate(tab)}>{label}<span aria-hidden="true"> →</span></button>;
  const stats = [
    ["PEOPLE", "students", classroom.active_member_count], ["ASSIGNMENT_ACTIVITY", "active", assignments.filter(item => item.status === "ACTIVE").length],
    ["DISCUSSION", "upcoming", deadlinesReady ? upcoming.length : null], ["RESOURCE_ACTIVITY", "resources", classwork ? sharedResourceCount(classwork) : null],
  ] as const;
  return <aside className="stream-sidebar" aria-label={tt("overview")}>
    <SidebarSection title={tt("overview")} action={all("classwork", tt("details"))}><dl className="stream-metrics">{stats.map(([kind, label, value]) => <div key={label}><dt><span className="stream-metric-icon" data-kind={kind}><StreamGlyph kind={kind} /></span>{tt(label)}</dt><dd>{value ?? tt("unavailable")}</dd></div>)}</dl>{!classwork ? <p className="classroom-meta">{tt(contentError ? "resourceError" : "resourceLoading")}</p> : null}</SidebarSection>
    <SidebarSection title={tt("upcoming")} action={all("calendar")}>
      {!deadlinesReady ? <p className="classroom-meta">{student && progress?.error ? tt("scheduleError") : ct("loading")}{student && progress?.error ? <button type="button" className="classroom-text-button" onClick={() => void progress.refresh()}>{ct("retry")}</button> : null}</p> : upcoming.length ? <ul className="stream-upcoming">{upcoming.slice(0, 3).map(({ assignment, date, kind }) => <li key={assignment.id}><button type="button" onClick={() => onOpenAssignment(assignment.id)}><span className="stream-resource-icon" data-kind={assignment.target?.module ?? "ASSIGNMENT_ACTIVITY"}><StreamGlyph kind="ASSIGNMENT_ACTIVITY" /></span><span className="stream-upcoming-title"><strong>{assignment.title ?? assignment.version?.test_title ?? ct("assignmentActivity")}</strong><AssignmentTargetSummary assignment={assignment} /></span><span className="stream-deadline"><small>{tt(kind)}</small><StreamTime value={date} /></span></button></li>)}</ul> : <p className="classroom-meta">{tt("noUpcoming")}</p>}
    </SidebarSection>
    <SidebarSection title={tt("members")} action={canViewRoster ? all("people") : undefined}>
      <ul className="stream-members">{classroom.teacher_name ? <li><StreamAvatar name={classroom.teacher_name} /><span><strong>{classroom.teacher_name}</strong><small>{tt("teacher")}</small></span></li> : null}{canViewRoster ? members?.filter(item => item.user_id !== classroom.teacher_id).slice(0, 3).map(member => <li key={member.user_id}><StreamAvatar name={member.display_name} /><span><strong>{member.display_name}</strong><small>{tt("student")}</small></span></li>) : null}</ul>
      {!canViewRoster ? <p className="classroom-meta">{tt("rosterRestricted")}</p> : members === undefined ? <p className="classroom-meta">{tt("rosterUnavailable")}</p> : !members.length ? <p className="classroom-meta">{tt("rosterEmpty")}</p> : null}
    </SidebarSection>
    <SidebarSection title={tt("recent")} action={onShowFeed ? <button type="button" className="stream-sidebar-link" onClick={onShowFeed}>{tt("viewAll")}<span aria-hidden="true"> →</span></button> : undefined}><p className="classroom-meta stream-recent-scope">{tt("recentScope")}</p>{recent.length ? <ul className="stream-recent">{recent.map(post => <li key={`${post.kind}-${post.id}`}><button type="button" onClick={() => { if (post.assignment_id) onOpenAssignment(post.assignment_id); else { const node = document.getElementById(`post-${post.id}`); node?.scrollIntoView?.({ block: "nearest" }); node?.focus(); } }}><span className="stream-resource-icon" data-kind={post.kind}><StreamGlyph kind={post.kind} /></span><span><strong>{post.author_name}</strong><small>{ct(post.kind === "ANNOUNCEMENT" ? "announcement" : post.kind === "DISCUSSION" ? "discussion" : post.kind === "ASSIGNMENT_ACTIVITY" ? "assignmentActivity" : "resourceActivity")} · {ct(post.status === "DRAFT" ? "draft" : post.status === "ARCHIVED" ? "archived" : "published")}</small></span><StreamTime value={post.created_at} /></button></li>)}</ul> : <p className="classroom-meta">{tt("noActivity")}</p>}</SidebarSection>
  </aside>;
}
