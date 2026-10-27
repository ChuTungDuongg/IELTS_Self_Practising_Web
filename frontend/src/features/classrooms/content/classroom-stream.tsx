"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPost, listFeed, type ClassroomPost, type ClassroomResource, type ContentStatus } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { PostComposer } from "./post-composer";
import { PostCard } from "./post-card";
import { useLmsText } from "../lms/messages";
import { ApiError } from "@/lib/api/client";
export function ClassroomStream({ classroomId, resources, userId, canAuthor, canModerate = canAuthor, canInspect, archived, admin, onOpenAssignment, initialCompose = false, selectedPostId = null }: {
  classroomId: string; resources: ClassroomResource[]; userId: string; canAuthor: boolean; canModerate?: boolean; initialCompose?: boolean; canInspect: boolean; archived: boolean; admin: boolean; onOpenAssignment: (id: string) => void; selectedPostId?: string | null;
}) {
  const { ct } = useContentTranslation();
  const { lt } = useLmsText();
  const [kind, setKind] = useState<ClassroomPost["kind"] | "">("");
  const [items, setItems] = useState<ClassroomPost[]>([]), [cursor, setCursor] = useState<string | null>(null), [status, setStatus] = useState<ContentStatus | "">("");
  const [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [composing, setComposing] = useState(initialCompose), [selected, setSelected] = useState<ClassroomPost | null>(null);
  const requestId = useRef(0);
  const load = useCallback(async (next?: string, signal?: AbortSignal) => {
    const sequence = ++requestId.current; setLoading(true); setError(null);
    try { const result = await listFeed(classroomId, { ...(next ? { cursor: next } : {}), ...(status ? { status } : {}), ...(kind ? { contentKind: kind } : {}), ...(signal ? { signal } : {}) }); if (sequence !== requestId.current || signal?.aborted) return; setItems(previous => next ? [...previous, ...result.items.filter(item => !previous.some(old => old.id === item.id && old.kind === item.kind))] : result.items); setCursor(result.next_cursor); }
    catch (caught) { if (sequence === requestId.current && !signal?.aborted) setError(contentError(caught, ct("error"))); } finally { if (sequence === requestId.current && !signal?.aborted) setLoading(false); }
  }, [classroomId, status, kind, ct]);
  useEffect(() => { const controller = new AbortController(); void Promise.resolve().then(() => { if (!controller.signal.aborted) void load(undefined, controller.signal); }); return () => controller.abort(); }, [load]);
  useEffect(() => {
    const id = selectedPostId; if (!id) return;
    const controller = new AbortController(); void getPost(classroomId, id, controller.signal).then(post => { if (!controller.signal.aborted) setSelected(post); }).catch(caught => { if (!controller.signal.aborted) setError(caught instanceof ApiError && caught.code === "CLASSROOM_POST_NOT_FOUND" ? ct("unavailablePost") : contentError(caught, ct("error"))); });
    return () => controller.abort();
  }, [classroomId, selectedPostId, ct]);
  async function refresh() { await load(); if (selected) { try { setSelected(await getPost(classroomId, selected.id)); } catch { setSelected(null); } } }
  const activeSelection = selected?.id === selectedPostId ? selected : null;
  const shown = activeSelection ? [activeSelection, ...items.filter(item => item.id !== activeSelection.id || item.kind !== activeSelection.kind)] : items;
  return <section className="classroom-stream" aria-label={ct("updates")}>
    <div className="classroom-section-heading"><h2>{ct("stream")}</h2><div className="classroom-toolbar"><label className="classroom-filter"><span className="sr-only">{lt("filterFeed")}</span><select className="select-field" value={kind} onChange={event => { setKind(event.target.value as typeof kind); setSelected(null); }}><option value="">{lt("allContent")}</option><option value="ANNOUNCEMENT">{lt("announcements")}</option><option value="DISCUSSION">{lt("discussions")}</option><option value="ASSIGNMENT_ACTIVITY">{lt("assignments")}</option><option value="RESOURCE_ACTIVITY">{ct("resourceActivity")}</option></select></label>{canInspect ? <label className="classroom-filter"><span className="sr-only">{ct("filter")}</span><select className="select-field" value={status} onChange={event => { setStatus(event.target.value as typeof status); setSelected(null); }}><option value="">{ct("all")}</option><option value="PUBLISHED">{ct("published")}</option><option value="DRAFT">{ct("draft")}</option><option value="ARCHIVED">{ct("archived")}</option></select></label> : null}{canAuthor && !archived && !composing ? <button className="btn btn-primary" type="button" onClick={() => setComposing(true)}>{ct("newPost")}</button> : null}</div></div>
    {composing && !archived && canAuthor ? <PostComposer classroomId={classroomId} resources={resources} onCancel={() => setComposing(false)} onDone={async () => { setComposing(false); await refresh(); }} /> : null}
    {loading && !shown.length ? <div className="classroom-panel classroom-skeleton" role="status"><p>{ct("loading")}</p><div /><div /></div> : null}
    {error ? <div className="classroom-panel"><p className="notice notice-error" role="alert">{error}</p><button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void load()}>{ct("retry")}</button></div> : null}
    {!loading && !error && !shown.length ? <p className="classroom-empty">{ct("emptyFeed")}</p> : null}
    {shown.map(post => <PostCard key={`${post.kind}-${post.id}`} classroomId={classroomId} post={post} resources={resources} userId={userId} canAuthor={canAuthor} canModerate={canModerate} archived={archived} admin={admin} onRefresh={refresh} onOpenAssignment={onOpenAssignment} initialComments={post.id === activeSelection?.id} />)}
    {cursor ? <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void load(cursor)}>{ct("loadMore")}</button> : null}
  </section>;
}
