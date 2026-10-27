"use client";

import { useLmsText } from "../lms/messages";
import { useEffect, useId, useState } from "react";
import { getPost, postAction, updatePost, type ClassroomPost, type ClassroomResource } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { SafeMarkdown } from "./safe-markdown";
import { PostComposer } from "./post-composer";
import { PostComments } from "./post-comments";
import { useAssignmentProgress } from "../scheduling/progress-provider";
import { deletePost } from "@/lib/api/classroom-content";
import { ActionMenu } from "../lms/action-menu";
import { StreamAvatar, StreamBadge, StreamGlyph, StreamTime } from "./stream/identity";
import { StreamAssignmentPreview, StreamResourcePreview } from "./stream/previews";
import { useStreamText } from "./stream/messages";
export function PostCard({ classroomId, post, resources, userId, canAuthor, canModerate = canAuthor, archived, admin, onRefresh, onOpenAssignment, initialComments = false }: {
  classroomId: string; post: ClassroomPost; resources: ClassroomResource[]; userId: string; canAuthor: boolean; canModerate?: boolean; archived: boolean; admin: boolean;
  onRefresh: () => Promise<unknown>; onOpenAssignment: (id: string) => void; initialComments?: boolean;
}) {
  const { ct } = useContentTranslation(), { lt } = useLmsText(), { tt } = useStreamText(); const [editing, setEditing] = useState(false), [comments, setComments] = useState(initialComments);
  const commentsId = useId();
  const [count, setCount] = useState({ source: post.comment_count, value: post.comment_count }), [countError, setCountError] = useState(false);
  if (count.source !== post.comment_count) setCount({ source: post.comment_count, value: post.comment_count });
  async function refreshCount() {
    try { const updated = await getPost(classroomId, post.id); setCount(current => ({ ...current, value: updated.comment_count })); setCountError(false); }
    catch { setCountError(true); }
  }
  useEffect(() => { if (!initialComments) return; const frame = requestAnimationFrame(() => setComments(true)); return () => cancelAnimationFrame(frame); }, [initialComments]);
  const isAssignment = post.kind === "ASSIGNMENT_ACTIVITY", isResource = post.kind === "RESOURCE_ACTIVITY";
  const isActivity = isAssignment || isResource, author = canAuthor && !archived && !admin, moderator = canModerate && !archived && !admin, canEdit = author && post.status !== "ARCHIVED";
  const progress = useAssignmentProgress(), assignment = progress?.assignments.find(item => item.id === post.assignment_id);
  const kindLabel = ct(isResource ? "resourceActivity" : isAssignment ? "assignmentActivity" : post.kind === "ANNOUNCEMENT" ? "announcement" : "discussion");
  const title = post.title?.trim() || assignment?.title?.trim() || assignment?.version?.test_title || kindLabel;
  if (editing && canEdit && !isActivity) return <PostComposer classroomId={classroomId} post={post} resources={resources} onCancel={() => setEditing(false)} onDone={async () => { await onRefresh(); setEditing(false); }} />;
  const date = new Date(post.created_at), edited = new Date(post.updated_at).valueOf() > date.valueOf();
  return <article className={`classroom-panel classroom-post stream-post classroom-post-${post.kind.toLowerCase()}`} id={`post-${post.id}`} tabIndex={-1}>
    <div className="stream-post-avatar"><StreamAvatar name={post.author_name} /></div><div className="stream-post-content">
    <header className="classroom-post-header">
      <div><div className="stream-badges"><StreamBadge post={post} />{post.pinned ? <span className="stream-pinned"><StreamGlyph kind="PIN" />{ct("pinned")}</span> : null}{post.status !== "PUBLISHED" ? <span className="stream-pinned">{ct(post.status === "DRAFT" ? "draft" : "archived")}</span> : null}</div><strong className="stream-author">{post.author_name}</strong><p className="classroom-meta stream-author-meta">{tt(post.author_role === "TEACHER" ? "teacher" : post.author_role === "ADMIN" ? "admin" : "author")} · <StreamTime value={post.created_at} />{edited ? ` · ${ct("edited")}` : ""}</p></div>
    </header>
    <h3>{title}</h3>
    <SafeMarkdown text={post.body} />
    {isResource && post.resource ? <>{post.resource_topic ? <p className="classroom-meta">{ct("resourceTopic", { name: post.resource_topic })}</p> : null}<StreamResourcePreview resource={post.resource} /></> : post.resource_ids.length ? <ul className="stream-attachments">{post.resource_ids.map(id => { const resource = resources.find(item => item.id === id); return <li key={id}>{resource ? <StreamResourcePreview resource={resource} /> : <p className="classroom-meta">{tt("attachUnavailable")}</p>}</li>; })}</ul> : null}
    {isAssignment && post.assignment_id ? <StreamAssignmentPreview assignment={assignment} id={post.assignment_id} title={title} onOpen={onOpenAssignment} /> : null}
    <footer className="stream-post-footer">
    {(author || moderator) && !isActivity ? <ActionMenu label={lt("more")} iconOnly>{canEdit ? <>
      <button type="button" className="classroom-text-button" onClick={() => setEditing(true)}>{ct("edit")}</button>
      {post.status === "DRAFT" ? <ContentAction action={() => postAction(classroomId, post.id, "publish")} onDone={onRefresh}>{ct("publish")}</ContentAction> : <ContentAction action={() => updatePost(classroomId, post.id, { status: "DRAFT" })} onDone={onRefresh}>{ct("unpublish")}</ContentAction>}
      {post.kind === "ANNOUNCEMENT" && post.status === "PUBLISHED" ? <ContentAction action={() => postAction(classroomId, post.id, "pin", !post.pinned)} onDone={onRefresh}>{ct(post.pinned ? "unpin" : "pin")}</ContentAction> : null}
      </> : null}{moderator ? <ContentAction action={() => updatePost(classroomId, post.id, { locked: !post.locked })} onDone={onRefresh}>{ct(post.locked ? "unlock" : "lock")}</ContentAction> : null}
      {canEdit ? <ContentAction action={() => postAction(classroomId, post.id, "archive")} onDone={onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction> : null}
      {author ? <ContentAction action={() => deletePost(classroomId, post.id)} onDone={onRefresh} confirm={{ title: ct("deletePostTitle"), description: ct("deletePostDescription") }}>{ct("delete")}</ContentAction> : null}
    </ActionMenu> : null}
    {!isActivity ? <button type="button" className="stream-comment-toggle" aria-expanded={comments} aria-controls={commentsId} onClick={() => setComments(value => !value)}><StreamGlyph kind="DISCUSSION" />{ct("comments")} ({count.value})</button> : post.assignment_id ? <button className="classroom-text-button" type="button" onClick={() => onOpenAssignment(post.assignment_id!)}>{ct(post.status === "ARCHIVED" ? "viewDetails" : "openAssignment")}</button> : null}
    </footer>
    {!isActivity ? <>
      {post.locked ? <p className="classroom-meta">{ct("locked")}</p> : null}
      {countError ? <p role="alert" className="classroom-meta">{ct("refreshFailed")} <button type="button" className="classroom-text-button" onClick={() => void refreshCount()}>{ct("retry")}</button></p> : null}
      {comments ? <div id={commentsId}><PostComments classroomId={classroomId} postId={post.id} userId={userId} canModerate={moderator} readOnly={archived || admin || post.status !== "PUBLISHED"} locked={post.locked} onCountChange={() => void refreshCount()} /></div> : null}
    </> : null}
    </div>
  </article>;
}
