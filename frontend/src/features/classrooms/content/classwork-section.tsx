"use client";

import { useState } from "react";
import { AlertIcon, ArchiveIcon, PlusIcon, ReadingIcon, SearchIcon } from "@/components/ui/icons";
import { TopicChevronIcon, TopicFolderIcon } from "./classwork-icons";
import { updateSection, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { ClassworkItemRow } from "./classwork-item-row";
import { ActionMenu } from "../lms/action-menu";
import { useLmsText } from "../lms/messages";
import type { ClassworkGroup } from "./classwork-groups";
import { searchClasswork } from "./classwork-search";

export type ClassworkSectionActions = {
  onAssignmentsChanged: () => Promise<unknown>;
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
  onDeleteSection: (id: string) => Promise<unknown>;
  onDeleteResource: (id: string) => Promise<unknown>;
  onRemoveAssignment: (id: string) => Promise<unknown>;
};

export function ClassworkSection({ group, index, sections, classroomId, canAuthor, canAssign, canInspect, pending, actions, expanded, onToggle }: {
  group: ClassworkGroup; index: number; sections: ClassroomSection[]; classroomId: string; canAuthor: boolean; canAssign: boolean; canInspect: boolean; pending: boolean;
  actions: ClassworkSectionActions; expanded: boolean; onToggle: () => void;
}) {
  const { ct } = useContentTranslation(), { lt } = useLmsText();
  const { section, rows, kind, key } = group, id = section?.id ?? null;
  const [archiveQuery, setArchiveQuery] = useState("");
  const history = kind === "archivedAssignments" || kind === "archivedResources" || section?.status === "ARCHIVED";
  const archiveGroup = kind === "archivedAssignments" || kind === "archivedResources";
  const title = section?.title ?? ct(kind === "unplaced" ? "uncategorized" : kind === "archivedAssignments" ? "archivedAssignments" : "archivedResources");
  const editable = canAuthor && !history;
  const count = !rows.length ? ct("emptyTopicCount") : kind === "archivedAssignments" ? ct(rows.length === 1 ? "archivedCountOne" : "archivedCount", { name: String(rows.length) }) : ct(rows.length === 1 ? "itemCountOne" : "itemCount", { name: String(rows.length) });
  const Icon = archiveGroup || history ? ArchiveIcon : TopicFolderIcon;
  const visibleRows = archiveGroup ? searchClasswork([group], archiveQuery)[0]?.rows ?? [] : rows;
  return <section id={key} data-archived={!!history} className={"classroom-course-section" + (kind !== "topic" ? " classroom-secondary-group" : "") + (archiveGroup ? " classroom-archive-group" : "")} aria-label={title} aria-busy={pending}
    onDragOver={event => { if (editable) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }}
    onDrop={event => { if (editable) { event.preventDefault(); actions.onSectionDrop(id); } }} onDragEnd={actions.onDragEnd}>
    <header className="classroom-topic-header">
      <h3><button id={key + "-toggle"} className="classroom-topic-toggle" type="button" aria-expanded={expanded} aria-controls={key + "-content"} onClick={onToggle}>
        <TopicChevronIcon className="classroom-topic-chevron" /><Icon className="classroom-topic-icon" /><span className="classroom-topic-label">{archiveGroup ? <><span className="classroom-topic-title-line"><span className="classroom-topic-name">{title}</span><span className="classroom-topic-count">{count}</span></span><span className="classroom-archive-description">{ct("archiveDescriptionShort")}</span></> : <><span className="classroom-topic-name">{title}</span><span className="classroom-topic-count">{count}</span></>}</span>
      </button></h3>
      {archiveGroup ? <label className="classroom-content-search classroom-archive-search"><SearchIcon /><span className="sr-only">{ct(kind === "archivedAssignments" ? "searchArchivedAssignments" : "searchArchivedResources")}</span><input type="search" value={archiveQuery} placeholder={ct(kind === "archivedAssignments" ? "searchArchivedAssignmentsPlaceholder" : "searchArchivedResourcesPlaceholder")} onChange={event => { setArchiveQuery(event.target.value); if (!expanded) onToggle(); }} /></label> : null}
      {canAuthor && section ? <ActionMenu label={lt("topicActions")} iconOnly>
        {section.status === "ARCHIVED" ? <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: "DRAFT" })} onDone={actions.onRefresh} confirm={{ title: ct("restoreDraftTitle"), description: ct("restoreDraftDescription") }}>{ct("restore")}</ContentAction> : null}
        <button className="classroom-order-button" type="button" disabled={pending || index === 0} aria-label={ct("moveUp", { name: section.title })} onClick={() => actions.onSectionStep(section.id, -1)}>↑</button>
        <button className="classroom-order-button" type="button" disabled={pending || index === sections.length - 1} aria-label={ct("moveDown", { name: section.title })} onClick={() => actions.onSectionStep(section.id, 1)}>↓</button>
        <button className="classroom-drag-handle" type="button" disabled={pending} draggable={!pending} aria-label={ct("dragSection") + ": " + section.title} onDragStart={event => { actions.onSectionDrag(section.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", section.id); }}>⠿</button>
        {section.status !== "ARCHIVED" ? <>
          <button type="button" disabled={pending} onClick={() => actions.onEditSection(section)}>{ct("edit")}</button>
          <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: section.status === "DRAFT" ? "PUBLISHED" : "DRAFT" })} onDone={actions.onRefresh}>{ct(section.status === "DRAFT" ? "publish" : "unpublish")}</ContentAction>
          <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: "ARCHIVED" })} onDone={actions.onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction>
          {rows.length || !expanded ? <button type="button" disabled={pending} onClick={() => actions.onAddResource(id)}>{ct("addResource")}</button> : null}
          {canAssign ? <button type="button" disabled={pending} onClick={() => actions.onAttachAssignment(id)}>{ct("attachAssignment")}</button> : null}
        </> : null}
        <ContentAction disabled={pending} action={() => actions.onDeleteSection(section.id)} confirm={{ title: ct("deleteTopicTitle"), description: ct("deleteTopicDescription") }}>{ct("delete")}</ContentAction>
      </ActionMenu> : null}
    </header>
    <div id={key + "-content"} hidden={!expanded} aria-labelledby={key + "-toggle"} className="classroom-topic-body">
      {expanded ? <>
        {section && canAuthor && section.status !== "PUBLISHED" ? <p className="classroom-meta">{ct(section.status === "DRAFT" ? "draft" : "archived")}</p> : null}
        {section?.description ? <p className="classroom-topic-description">{section.description}</p> : null}
        {visibleRows.length ? <ul className="classroom-classwork-list">{visibleRows.map((row, itemIndex) => <ClassworkItemRow key={row.key} item={row.item} resource={row.resource} assignment={row.assignment}
          classroomId={classroomId} sections={sections} canAuthor={canAuthor} canAssign={canAssign} canInspect={canInspect} pending={pending} first={itemIndex === 0} last={itemIndex === visibleRows.length - 1}
          onEdit={actions.onEditResource} onRefresh={actions.onRefresh} onMove={actions.onItemMove} onPlace={actions.onPlaceAssignment} onStep={actions.onItemStep} onDrag={actions.onItemDrag}
          onDelete={actions.onDeleteResource} onRemove={actions.onRemoveAssignment} onAssignmentsChanged={actions.onAssignmentsChanged}
          onDrop={beforeId => actions.onItemDrop(id, beforeId)} onOpenAssignment={actions.onOpenAssignment} />)}</ul> : archiveGroup ? <p className="classroom-meta classroom-archive-empty" role="status">{ct("noSearchResults")}</p> : <div className="classroom-topic-empty"><ReadingIcon /><p>{ct("emptyTopic")}</p>{editable ? <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => actions.onAddResource(id)}><PlusIcon />{lt("create")}</button> : null}</div>}
        {archiveGroup ? <p className="classroom-archive-notice"><AlertIcon /><span>{ct(kind === "archivedAssignments" ? "archiveNotice" : "resourceArchiveNotice")}</span></p> : null}
      </> : null}
    </div>
  </section>;
}
