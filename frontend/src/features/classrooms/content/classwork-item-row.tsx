"use client";

import Link from "next/link";
import { BuilderIcon, ReadingIcon } from "@/components/ui/icons";
import { updateResource, type ClassworkItem, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { ResourceViewer } from "./resource-viewer";
import { ActionMenu } from "../lms/action-menu";
import { useAssignmentProgress } from "../scheduling/progress-provider";
import { ClassworkAssignmentMeta } from "./classwork-assignment-meta";
import { ArchivedAssignmentActions } from "./archived-assignment-actions";
import { ArchiveActionLayout } from "./archive-action-layout";

export function ClassworkItemRow({ item, resource, assignment, classroomId, sections, canAuthor, canAssign, canInspect, pending, first, last, onEdit, onRefresh, onMove, onPlace, onStep, onDrag, onDrop, onOpenAssignment, onDelete, onRemove, onAssignmentsChanged }: {
  item?: ClassworkItem; resource?: ClassroomResource; assignment?: ClassroomAssignment; classroomId: string; sections: ClassroomSection[]; canAuthor: boolean; canAssign: boolean; canInspect: boolean; pending: boolean; first: boolean; last: boolean;
  onEdit: (resource: ClassroomResource) => void; onRefresh: () => Promise<unknown>; onMove: (id: string, sectionId: string | null) => void; onPlace: (id: string, sectionId: string | null) => void; onStep: (id: string, delta: number) => void;
  onDrag: (id: string) => void; onDrop: (id: string) => void; onOpenAssignment: (id: string) => void;
  onDelete: (id: string) => Promise<unknown>; onRemove: (id: string) => Promise<unknown>;
  onAssignmentsChanged: () => Promise<unknown>;
}) {
  const { ct, locale } = useContentTranslation(), progress = useAssignmentProgress();
  const title = resource?.title ?? assignment?.title ?? assignment?.version?.test_title ?? ct("assignmentActivity");
  const archived = resource?.status === "ARCHIVED" || assignment?.status === "ARCHIVED";
  const result = assignment && !canInspect && !progress?.staff ? progress?.items[assignment.id]?.result_attempt_id : null;
  const Icon = resource ? ReadingIcon : BuilderIcon;
  const canManage = assignment ? canAssign : canAuthor;
  if (!resource && !assignment) return null;
  const archivedAt = assignment?.archived_at;
  return <li id={"classwork-" + (assignment ? "assignment-" + assignment.id : "resource-" + resource!.id)} tabIndex={-1} className={"classroom-classwork-row" + (archived ? " classroom-archived-row" : "")}
    onDragOver={event => { if (canAuthor && item && !archived) { event.preventDefault(); event.stopPropagation(); } }}
    onDrop={event => { if (canAuthor && item && !archived) { event.preventDefault(); event.stopPropagation(); onDrop(item.id); } }}>
    <div className="classroom-item-identity"><Icon className="classroom-item-icon" /><div><h4>{title}</h4>
      {assignment && archived && canInspect ? <p className="classroom-meta">{ct("assignmentActivity")} · {ct("archived")}</p> : assignment ? <ClassworkAssignmentMeta assignment={assignment} /> : resource ? <p className="classroom-meta">{ct(resource.kind === "TEXT" ? "text" : resource.kind === "LINK" ? "link" : "file")}{resource.status !== "PUBLISHED" ? " · " + ct(resource.status === "DRAFT" ? "draft" : "archived") : ""}</p> : null}
    </div></div>
    {archived && archivedAt && Number.isFinite(Date.parse(archivedAt)) ? <time className="classroom-archive-date" dateTime={archivedAt}>{ct("archivedOn", { name: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(new Date(archivedAt)) })}</time> : null}
    {resource ? <ResourceViewer resource={resource} compact /> : assignment && !(archived && canManage) ? <div className="classroom-item-navigation">{result ? <Link className="classroom-text-button" href={"/review/" + result}>{ct("viewResults")}</Link> : null}<button className={archived ? "btn btn-secondary" : "classroom-text-button"} type="button" onClick={() => onOpenAssignment(assignment.id)}>{ct("viewDetails")}</button></div> : null}
    {archived && assignment && canManage ? <ArchivedAssignmentActions assignment={assignment} onChanged={onAssignmentsChanged} onDetails={() => onOpenAssignment(assignment.id)} disabled={pending} /> : null}
    {archived && resource && canManage ? <ArchiveActionLayout>
      <ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: "DRAFT" })} onDone={onRefresh} confirm={{ title: ct("restoreDraftTitle"), description: ct("restoreDraftDescription") }}>{ct("restore")}</ContentAction>
      <ContentAction disabled={pending} action={() => onDelete(resource.id)} confirm={{ title: ct("deleteResourceTitle"), description: ct("deleteResourceDescription") }}>{ct("delete")}</ContentAction>
    </ArchiveActionLayout> : null}
    {canManage && !archived ? <ActionMenu label={ct("itemActions")} iconOnly>
      {item && !archived ? <button className="classroom-drag-handle" type="button" draggable={!pending} disabled={pending} aria-label={ct("dragItem") + ": " + title} onDragStart={event => { event.stopPropagation(); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.id); onDrag(item.id); }}>⠿</button> : null}
      {resource && !archived ? <>
        <button type="button" disabled={pending} onClick={() => onEdit(resource)}>{ct("edit")}</button>
        <ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: resource.status === "DRAFT" ? "PUBLISHED" : "DRAFT" })} onDone={onRefresh}>{ct(resource.status === "DRAFT" ? "publish" : "unpublish")}</ContentAction>
        <ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: "ARCHIVED" })} onDone={onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction>
      </> : null}
      {item ? <div className="classroom-toolbar"><button type="button" className="classroom-order-button" disabled={pending || first} aria-label={ct("moveUp", { name: title })} onClick={() => onStep(item.id, -1)}>↑</button><button type="button" className="classroom-order-button" disabled={pending || last} aria-label={ct("moveDown", { name: title })} onClick={() => onStep(item.id, 1)}>↓</button></div> : null}
      {item || assignment && !archived ? <label className="classroom-move-label"><span className="sr-only">{ct("moveTo", { name: title })}</span><select className="select-field" value={item?.section_id ?? ""} disabled={pending} onChange={event => item ? onMove(item.id, event.target.value || null) : onPlace(assignment!.id, event.target.value || null)}><option value="">{ct("uncategorized")}</option>{sections.filter(section => section.status !== "ARCHIVED" || section.id === item?.section_id).map(section => <option key={section.id} value={section.id}>{section.title}</option>)}</select></label> : null}
      {resource ? <ContentAction disabled={pending} action={() => onDelete(resource.id)} confirm={{ title: ct("deleteResourceTitle"), description: ct("deleteResourceDescription") }}>{ct("delete")}</ContentAction> : item && assignment && !archived ? <ContentAction disabled={pending} action={() => onRemove(item.id)} confirm={{ title: ct("removeAssignmentTitle"), description: ct("removeAssignmentDescription") }}>{ct("remove")}</ContentAction> : null}
    </ActionMenu> : null}
  </li>;
}
