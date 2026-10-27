"use client";

import { ArrowIcon } from "@/components/ui/icons";
import { updateSection, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { ClassworkItemRow } from "./classwork-item-row";
import { ActionMenu } from "../lms/action-menu";
import { useLmsText } from "../lms/messages";
import type { ClassworkGroup } from "./classwork-groups";

export type ClassworkSectionActions = {
  onEditSection: (section: ClassroomSection) => void;
  onEditResource: (resource: ClassroomResource) => void;
  onAddResource: (sectionId: string | null) => void;
  onAttachAssignment: (sectionId: string | null) => void;
  onRefresh: () => Promise<unknown>;
  onSectionStep: (id: string, delta: number) => void;
  onSectionDrag: (id: string) => void;
  onSectionDrop: (id: string | null) => void;
  onDragEnd: () => void;
  onItemMove: (id: string, sectionId: string | null) => void;
  onPlaceAssignment: (id: string, sectionId: string | null) => void;
  onItemStep: (id: string, delta: number) => void;
  onItemDrag: (id: string) => void;
  onItemDrop: (sectionId: string | null, beforeId?: string) => void;
  onOpenAssignment: (id: string) => void;
};

export function ClassworkSection({ group, index, sections, classroomId, canAuthor, pending, actions, expanded, onToggle }: {
  group: ClassworkGroup; index: number; sections: ClassroomSection[]; classroomId: string; canAuthor: boolean; pending: boolean;
  actions: ClassworkSectionActions; expanded: boolean; onToggle: () => void;
}) {
  const { ct } = useContentTranslation(), { lt } = useLmsText();
  const { section, rows, kind, key } = group, id = section?.id ?? null;
  const history = kind === "archivedAssignments" || kind === "archivedResources";
  const title = section?.title ?? ct(kind === "unplaced" ? "uncategorized" : kind === "archivedAssignments" ? "archivedAssignments" : "archivedResources");
  const editable = canAuthor && !history;
  const count = !rows.length ? ct("noContent") : kind === "archivedAssignments" ? ct(rows.length === 1 ? "archivedCountOne" : "archivedCount", { name: String(rows.length) }) : ct(rows.length === 1 ? "itemCountOne" : "itemCount", { name: String(rows.length) });
  return <section id={key} className={"classroom-course-section" + (kind !== "topic" ? " classroom-secondary-group" : "")} aria-label={title} aria-busy={pending}
    onDragOver={event => { if (editable) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }}
    onDrop={event => { if (editable) { event.preventDefault(); actions.onSectionDrop(id); } }} onDragEnd={actions.onDragEnd}>
    <header className="classroom-topic-header">
      <h3><button id={key + "-toggle"} className="classroom-topic-toggle" type="button" aria-expanded={expanded} aria-controls={key + "-content"} onClick={onToggle}>
        <ArrowIcon className="classroom-topic-chevron" /><span className="classroom-topic-name">{title}</span><span className="classroom-topic-count">{count}</span>
      </button></h3>
      {canAuthor && section ? <ActionMenu label={lt("topicActions")} iconOnly>
        <button className="classroom-order-button" type="button" disabled={pending || index === 0} aria-label={ct("moveUp", { name: section.title })} onClick={() => actions.onSectionStep(section.id, -1)}>↑</button>
        <button className="classroom-order-button" type="button" disabled={pending || index === sections.length - 1} aria-label={ct("moveDown", { name: section.title })} onClick={() => actions.onSectionStep(section.id, 1)}>↓</button>
        <button className="classroom-drag-handle" type="button" disabled={pending} draggable={!pending} aria-label={ct("dragSection") + ": " + section.title} onDragStart={event => { actions.onSectionDrag(section.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", section.id); }}>⠿</button>
        {section.status !== "ARCHIVED" ? <>
          <button type="button" disabled={pending} onClick={() => actions.onEditSection(section)}>{ct("edit")}</button>
          <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: section.status === "DRAFT" ? "PUBLISHED" : "DRAFT" })} onDone={actions.onRefresh}>{ct(section.status === "DRAFT" ? "publish" : "unpublish")}</ContentAction>
          <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: "ARCHIVED" })} onDone={actions.onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction>
          {rows.length || !expanded ? <button type="button" disabled={pending} onClick={() => actions.onAddResource(id)}>{ct("addResource")}</button> : null}
          <button type="button" disabled={pending} onClick={() => actions.onAttachAssignment(id)}>{ct("attachAssignment")}</button>
        </> : null}
      </ActionMenu> : null}
    </header>
    <div id={key + "-content"} hidden={!expanded} aria-labelledby={key + "-toggle"} className="classroom-topic-body">
      {expanded ? <>
        {section && canAuthor && section.status !== "PUBLISHED" ? <p className="classroom-meta">{ct(section.status === "DRAFT" ? "draft" : "archived")}</p> : null}
        {section?.description ? <p className="classroom-topic-description">{section.description}</p> : null}
        {rows.length ? <ul className="classroom-classwork-list">{rows.map((row, itemIndex) => <ClassworkItemRow key={row.key} item={row.item} resource={row.resource} assignment={row.assignment}
          classroomId={classroomId} sections={sections} canAuthor={canAuthor} pending={pending} first={itemIndex === 0} last={itemIndex === rows.length - 1}
          onEdit={actions.onEditResource} onRefresh={actions.onRefresh} onMove={actions.onItemMove} onPlace={actions.onPlaceAssignment} onStep={actions.onItemStep} onDrag={actions.onItemDrag}
          onDrop={beforeId => actions.onItemDrop(id, beforeId)} onOpenAssignment={actions.onOpenAssignment} />)}</ul> : <div className="classroom-topic-empty"><p>{ct("emptyTopic")}</p>{editable && section?.status !== "ARCHIVED" ? <button type="button" className="classroom-text-button" disabled={pending} onClick={() => actions.onAddResource(id)}>{ct("addResource")}</button> : null}</div>}
      </> : null}
    </div>
  </section>;
}
