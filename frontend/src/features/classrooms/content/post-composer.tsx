"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { createPost, updatePost, type ClassroomPost, type ClassroomResource } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
export function PostComposer({ classroomId, post, resources, onDone, onCancel }: {
  classroomId: string; post?: ClassroomPost; resources: ClassroomResource[]; onDone: () => Promise<unknown>; onCancel: () => void;
}) {
  const { ct } = useContentTranslation(), hintId = useId();
  const [kind, setKind] = useState<"ANNOUNCEMENT" | "DISCUSSION">(post?.kind === "DISCUSSION" ? "DISCUSSION" : "ANNOUNCEMENT");
  const [title, setTitle] = useState(post?.title ?? ""), [body, setBody] = useState(post?.body ?? "");
  const [attachments, setAttachments] = useState(post?.resource_ids ?? []), [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null);
  const running = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (running.current) return;
    if (!body.trim()) { setError(ct("bodyRequired")); return; }
    const publish = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "publish";
    running.current = true; setPending(true); setError(null);
    try {
      const input = { kind, title: title.trim() || null, body: body.trim(), resource_ids: attachments, status: (publish || post?.status === "PUBLISHED" ? "PUBLISHED" : "DRAFT") as "DRAFT" | "PUBLISHED" };
      if (post) await updatePost(classroomId, post.id, input); else await createPost(classroomId, input);
      await onDone();
    } catch (caught) { setError(contentError(caught, ct("error"))); }
    finally { running.current = false; setPending(false); }
  }
  return <form className="classroom-panel classroom-editor" onSubmit={submit} aria-label={ct(post ? "editPost" : "newPost")}>
    <h3>{ct(post ? "editPost" : "newPost")}</h3>
    <fieldset disabled={pending}>
      <label className="field-label">{ct("postType")}<select className="select-field" value={kind} onChange={event => setKind(event.target.value as typeof kind)}><option value="ANNOUNCEMENT">{ct("announcement")}</option><option value="DISCUSSION">{ct("discussion")}</option></select></label>
      <label className="field-label">{ct("optionalTitle")}<input className="field" maxLength={240} value={title} onChange={event => setTitle(event.target.value)} autoFocus /></label>
      <label className="field-label">{ct("message")}<textarea className="field" rows={6} maxLength={20000} value={body} onChange={event => setBody(event.target.value)} aria-describedby={hintId} /></label>
      <p id={hintId} className="classroom-meta">{ct("markdownHint")}</p>
      <details><summary>{ct("attachments")}</summary>{resources.length ? <div className="classroom-attachment-options">{resources.filter(item => item.status !== "ARCHIVED" || attachments.includes(item.id)).map(resource => <label key={resource.id}><input type="checkbox" checked={attachments.includes(resource.id)} onChange={event => setAttachments(previous => event.target.checked ? [...previous, resource.id] : previous.filter(id => id !== resource.id))} /> {resource.title} · {ct(resource.status === "PUBLISHED" ? "published" : resource.status === "DRAFT" ? "draft" : "archived")}</label>)}</div> : <p>{ct("emptyAttachments")}</p>}</details>
      <div className="classroom-toolbar">
        <button className="btn btn-primary" type="submit" value={post?.status === "PUBLISHED" ? "save" : "draft"}>{ct(pending ? "working" : post?.status === "PUBLISHED" ? "save" : "saveDraft")}</button>
        {post?.status !== "PUBLISHED" ? <button className="btn btn-secondary" type="submit" value="publish">{ct("publish")}</button> : null}
        <button className="btn btn-secondary" type="button" onClick={onCancel}>{ct("cancel")}</button>
      </div>
    </fieldset>
    {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
  </form>;
}
