"use client";

import { useState } from "react";
import { postAction, updatePost, type ClassroomPost, type ClassroomResource } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { SafeMarkdown } from "./safe-markdown";
import { PostComposer } from "./post-composer";
import { PostComments } from "./post-comments";
import { ResourceViewer } from "./resource-viewer";
import { ProgressSummary } from "../scheduling/progress-summary";
import { useAssignmentProgress } from "../scheduling/progress-provider";
export function PostCard({ classroomId, post, resources, userId, canAuthor, archived, admin, onRefresh, onOpenAssignment, initialComments = false }: {
  classroomId: string; post: ClassroomPost; resources: ClassroomResource[]; userId: string; canAuthor: boolean; archived: boolean; admin: boolean;
  onRefresh: () => Promise<unknown>; onOpenAssignment: (id: string) => void; initialComments?: boolean;
}) {
  const { ct, locale } = useContentTranslation(); const [editing, setEditing] = useState(false), [comments, setComments] = useState(initialComments);
  const isActivity = post.kind === "ASSIGNMENT_ACTIVITY", canEdit = canAuthor && !archived && post.status !== "ARCHIVED";
  const progress = useAssignmentProgress(), assignment = progress?.assignments.find(item => item.id === post.assignment_id);
  const title = post.title?.trim() || assignment?.title?.trim() || assignment?.version?.test_title || ct(isActivity ? "assignmentActivity" : post.kind === "ANNOUNCEMENT" ? "announcement" : "discussion");
  if (editing && canEdit && !isActivity) return <PostComposer classroomId={classroomId} post={post} resources={resources} onCancel={() => setEditing(false)} onDone={async () => { await onRefresh(); setEditing(false); }} />;
  const date = new Date(post.created_at), edited = new Date(post.updated_at).valueOf() > date.valueOf();
  return <article className={`classroom-panel classroom-post classroom-post-${post.kind.toLowerCase()}`} id={`post-${post.id}`} tabIndex={-1}>
    <header className="classroom-post-header">
      <div><p className="classroom-meta classroom-feed-kind">{ct(isActivity ? "assignmentActivity" : post.kind === "ANNOUNCEMENT" ? "announcement" : "discussion")}</p><h3>{title}</h3><p className="classroom-meta"><strong>{post.author_name}</strong> · {Number.isNaN(date.valueOf()) ? "" : <time dateTime={post.created_at}>{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(date)}</time>}{edited ? ` · ${ct("edited")}` : ""}</p></div>
      <div className="classroom-post-status">{post.pinned ? <span>{ct("pinned")}</span> : null}{post.status !== "PUBLISHED" ? <span>{ct(post.status === "DRAFT" ? "draft" : "archived")}</span> : null}</div>
    </header>
    <SafeMarkdown text={post.body} />
    {post.resource_ids.length ? <ul className="classroom-post-resources">{post.resource_ids.map(id => { const resource = resources.find(item => item.id === id); return resource ? <li key={id}><strong>{resource.title}</strong><ResourceViewer resource={resource} /></li> : null; })}</ul> : null}
    {isActivity && post.assignment_id ? <><ProgressSummary assignmentId={post.assignment_id} /><button className="btn btn-secondary" type="button" onClick={() => onOpenAssignment(post.assignment_id!)}>{ct("openAssignment")}</button></> : null}
    {canEdit && !isActivity ? <div className="classroom-toolbar">
      <button type="button" className="classroom-text-button" onClick={() => setEditing(true)}>{ct("edit")}</button>
      {post.status === "DRAFT" ? <ContentAction action={() => postAction(classroomId, post.id, "publish")} onDone={onRefresh}>{ct("publish")}</ContentAction> : <ContentAction action={() => updatePost(classroomId, post.id, { status: "DRAFT" })} onDone={onRefresh}>{ct("unpublish")}</ContentAction>}
      {post.kind === "ANNOUNCEMENT" && post.status === "PUBLISHED" ? <ContentAction action={() => postAction(classroomId, post.id, "pin", !post.pinned)} onDone={onRefresh}>{ct(post.pinned ? "unpin" : "pin")}</ContentAction> : null}
      <ContentAction action={() => updatePost(classroomId, post.id, { locked: !post.locked })} onDone={onRefresh}>{ct(post.locked ? "unlock" : "lock")}</ContentAction>
      <ContentAction action={() => postAction(classroomId, post.id, "archive")} onDone={onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction>
    </div> : null}
    {!isActivity ? <>
      <button type="button" className="classroom-text-button classroom-comments-toggle" aria-expanded={comments} onClick={() => setComments(value => !value)}>{ct("comments")} ({post.comment_count})</button>
      {post.locked ? <p className="classroom-meta">{ct("locked")}</p> : null}
      {comments ? <PostComments classroomId={classroomId} postId={post.id} userId={userId} canModerate={canAuthor} readOnly={archived || admin || post.status !== "PUBLISHED"} locked={post.locked} onCountChange={() => void onRefresh()} /> : null}
    </> : null}
  </article>;
}
