"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { listComments, createComment, updateComment, retractComment, type ClassroomComment } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { ContentAction, contentError } from "./content-action";
import { SafeMarkdown } from "./safe-markdown";
export function PostComments({ classroomId, postId, userId, canModerate, readOnly, locked = false, onCountChange }: {
  classroomId: string; postId: string; userId: string; canModerate: boolean; readOnly: boolean; locked?: boolean; onCountChange: () => void;
}) {
  const { ct, locale } = useContentTranslation();
  const [items, setItems] = useState<ClassroomComment[]>([]), [cursor, setCursor] = useState<string | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState(""), [editing, setEditing] = useState<string | null>(null), [pending, setPending] = useState(false);
  const running = useRef(false), formBody = useRef<HTMLTextAreaElement>(null);
  const load = useCallback(async (next?: string, signal?: AbortSignal) => {
    setLoading(true); setError(null);
    try { const result = await listComments(classroomId, postId, next, signal); if (signal?.aborted) return; setItems(previous => next ? [...previous, ...result.items.filter(item => !previous.some(old => old.id === item.id))] : result.items); setCursor(result.next_cursor); }
    catch (caught) { if (!signal?.aborted) setError(contentError(caught, ct("error"))); } finally { if (!signal?.aborted) setLoading(false); }
  }, [classroomId, postId, ct]);
  useEffect(() => { const controller = new AbortController(); void Promise.resolve().then(() => { if (!controller.signal.aborted) void load(undefined, controller.signal); }); return () => controller.abort(); }, [load]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!body.trim() || running.current) return; running.current = true; setPending(true); setError(null);
    try { if (editing) await updateComment(classroomId, editing, body.trim()); else await createComment(classroomId, postId, body.trim()); setBody(""); setEditing(null); await load(); onCountChange(); formBody.current?.focus(); }
    catch (caught) { setError(contentError(caught, ct("error"))); } finally { running.current = false; setPending(false); }
  }
  return <section className="classroom-comments" aria-label={ct("comments")}>
    {loading && !items.length ? <p role="status">{ct("loading")}</p> : !items.length ? <p className="classroom-meta">{ct("emptyComments")}</p> : null}
    <ol>{items.map(item => <li key={item.id} className="classroom-comment">
      <p className="classroom-meta"><strong>{item.author_name}</strong>{Number.isNaN(new Date(item.created_at).valueOf()) ? "" : ` · ${new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}`}{new Date(item.updated_at).valueOf() > new Date(item.created_at).valueOf() ? ` · ${ct("edited")}` : ""}</p>
      {item.state === "VISIBLE" ? <SafeMarkdown text={item.body} /> : <p className="classroom-meta">{ct(item.state === "RETRACTED" ? "removedComment" : "moderatedComment")}</p>}
      {!readOnly && item.state === "VISIBLE" ? <div className="classroom-toolbar">
        {item.author_id === userId ? <button className="classroom-text-button" type="button" disabled={pending} onClick={() => { setEditing(item.id); setBody(item.body); formBody.current?.focus(); }}>{ct("edit")}</button> : null}
        {item.author_id === userId || canModerate ? <ContentAction action={() => retractComment(classroomId, item.id)} onDone={async () => { await load(); onCountChange(); }} confirm={{ title: ct(item.author_id === userId ? "retractTitle" : "moderateTitle"), description: ct("commentRemoval") }}>{ct(item.author_id === userId ? "retract" : "moderate")}</ContentAction> : null}
      </div> : null}
    </li>)}</ol>
    {cursor ? <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void load(cursor)}>{ct("loadMore")}</button> : null}
    {error ? <div className="notice notice-error"><p role="alert">{error}</p><button type="button" className="classroom-text-button" disabled={loading} onClick={() => void load()}>{ct("retry")}</button></div> : null}
    {!readOnly && (!locked || editing) ? <form onSubmit={submit} className="classroom-comment-form">
      <label className="field-label">{ct("yourComment")}<textarea ref={formBody} className="field" value={body} onChange={event => setBody(event.target.value)} maxLength={5000} rows={3} required disabled={pending} /></label>
      <div className="classroom-toolbar"><button className="btn btn-secondary" disabled={pending || !body.trim()}>{ct(pending ? "working" : editing ? "save" : "sendComment")}</button>{editing ? <button type="button" className="classroom-text-button" onClick={() => { setEditing(null); setBody(""); }}>{ct("cancel")}</button> : null}</div>
    </form> : null}
  </section>;
}
