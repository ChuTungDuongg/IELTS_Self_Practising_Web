"use client";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import type { ClassroomResource } from "@/lib/api/classroom-content";
import { AssignmentTargetSummary } from "../../assignment-target";
import { useAssignmentProgress } from "../../scheduling/progress-provider";
import { ResourceViewer } from "../resource-viewer";
import { safeHttpUrl } from "../safe-markdown";
import { useContentTranslation } from "../content-messages";
import { StreamGlyph, StreamTime } from "./identity";
import { useStreamText } from "./messages";

export function StreamAssignmentPreview({ assignment, id, title, onOpen }: { assignment?: ClassroomAssignment; id: string; title: string; onOpen: (id: string) => void }) {
  const { tt } = useStreamText(), state = useAssignmentProgress();
  const own = state && !state.staff ? state.items[id] : undefined;
  const datesReady = !state || state.staff || !!own;
  const due = datesReady ? own ? own.effective_due_at : assignment?.due_at : null;
  const cutoff = datesReady ? own ? own.effective_cutoff_at : assignment?.cutoff_at : null;
  return <div className="stream-assignment-preview"><span className="stream-resource-icon" data-kind="ASSIGNMENT_ACTIVITY"><StreamGlyph kind="ASSIGNMENT_ACTIVITY" /></span><div className="stream-preview-title"><button type="button" onClick={() => onOpen(id)}>{title}</button>{assignment ? <AssignmentTargetSummary assignment={assignment} /> : null}</div><dl>{([ ["due", due], ["cutoff", cutoff] ] as const).map(([kind, date]) => date && Number.isFinite(Date.parse(date)) ? <div key={kind}><dt>{tt(kind)}</dt><dd><StreamTime value={date} /></dd></div> : null)}</dl></div>;
}
export function StreamResourcePreview({ resource }: { resource: ClassroomResource }) {
  const { tt, locale } = useStreamText(), { ct } = useContentTranslation();
  const url = resource.url ? safeHttpUrl(resource.url) : null;
  const filename = resource.original_filename || (url ? new URL(url).hostname : tt("text"));
  const size = resource.size_bytes == null ? "" : new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(resource.size_bytes / (resource.size_bytes >= 1024 * 1024 ? 1024 * 1024 : 1024)) + (resource.size_bytes >= 1024 * 1024 ? " MB" : " KB");
  return <div className="stream-resource-preview"><span className="stream-resource-icon" data-kind="RESOURCE_ACTIVITY"><StreamGlyph kind={resource.kind} /></span><div><strong>{filename}</strong><small>{[size, resource.kind === "FILE" ? resource.media_type ?? tt("file") : ct(resource.kind === "LINK" ? "link" : "text")].filter(Boolean).join(" · ")}</small></div><ResourceViewer resource={resource} compact /></div>;
}
