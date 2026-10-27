"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SearchIcon } from "@/components/ui/icons";
import { getPost, listFeed, type Classwork, type ClassroomPost, type ClassroomResource, type ContentStatus } from "@/lib/api/classroom-content";
import type { Classroom, ClassroomAssignment } from "@/lib/api/classrooms";
import { ApiError } from "@/lib/api/client";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { PostCard } from "./post-card";
import { StreamComposer } from "./stream/composer";
import { StreamSidebar, type StreamNavigation, type StreamRosterMember } from "./stream/sidebar";
import { useStreamText } from "./stream/messages";
import "./stream/stream.css";

type Props = {
  classroomId: string; resources: ClassroomResource[]; userId: string; userName?: string; canAuthor: boolean; canModerate?: boolean; initialCompose?: boolean; composeRequest?: number; canInspect: boolean; archived: boolean; admin: boolean; onOpenAssignment: (id: string) => void; selectedPostId?: string | null;
  classroom?: Classroom; assignments?: ClassroomAssignment[]; classwork?: Classwork | null; classworkError?: boolean; members?: StreamRosterMember[]; canViewRoster?: boolean; student?: boolean; onNavigate?: StreamNavigation; onResourcesChanged?: () => Promise<unknown>; active?: boolean;
};
export function ClassroomStream({ classroomId, resources, userId, userName, canAuthor, canModerate = canAuthor, canInspect, archived, admin, onOpenAssignment, initialCompose = false, composeRequest = 0, selectedPostId = null, classroom, assignments = [], classwork, classworkError, members, canViewRoster = false, student = false, onNavigate, onResourcesChanged, active = true }: Props) {
  const { ct } = useContentTranslation(), { tt } = useStreamText();
  const [filter, setFilter] = useState<ClassroomPost["kind"] | "PINNED" | "">(""), [status, setStatus] = useState<ContentStatus | "">("");
  const [query, setQuery] = useState(""), [search, setSearch] = useState("");
  const kind = filter && filter !== "PINNED" ? filter : undefined, pinnedOnly = filter === "PINNED";
  const scope = JSON.stringify([classroomId, status, kind, pinnedOnly, search]);
  const [page, setPage] = useState<{ scope: string; items: ClassroomPost[]; cursor: string | null }>({ scope, items: [], cursor: null });
  const [loading, setLoading] = useState(true), [loadError, setError] = useState<unknown>(null), [selected, setSelected] = useState<ClassroomPost | null>(null);
  const requestId = useRef(0), controller = useRef<AbortController | null>(null);
  const selectionRequest = useRef(0);
  const revision = `${classwork?.revision ?? ""}|${assignments.map(item => `${item.id}:${item.status}`).sort().join(",")}`;
  const visibleRevision = useRef(revision), previousActive = useRef(active);
  function clearSelection() { selectionRequest.current += 1; setSelected(null); }
  useEffect(() => { const timer = window.setTimeout(() => setSearch(query.trim()), 280); return () => window.clearTimeout(timer); }, [query]);
  const load = useCallback(async (next?: string) => {
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    const sequence = ++requestId.current; setLoading(true); setError(null);
    try {
      const result = await listFeed(classroomId, { ...(next ? { cursor: next } : {}), ...(status ? { status } : {}), ...(kind ? { contentKind: kind } : {}), ...(search ? { search } : {}), ...(pinnedOnly ? { pinnedOnly } : {}), signal: request.signal });
      if (sequence !== requestId.current || request.signal.aborted) return;
      setPage(previous => ({ scope, items: next && previous.scope === scope ? [...previous.items, ...result.items.filter(item => !previous.items.some(old => old.id === item.id && old.kind === item.kind))] : result.items, cursor: result.next_cursor }));
    } catch (caught) { if (sequence === requestId.current && !request.signal.aborted) { setError(caught); throw caught; } }
    finally { if (sequence === requestId.current && !request.signal.aborted) setLoading(false); }
  }, [classroomId, status, kind, search, pinnedOnly, scope]);
  useEffect(() => { let active = true; void Promise.resolve().then(() => { if (active) void load().catch(() => {}); }); return () => { active = false; controller.current?.abort(); }; }, [load]);
  useEffect(() => {
    const changedWhileAway = active && !previousActive.current && visibleRevision.current !== revision;
    previousActive.current = active;
    if (active) visibleRevision.current = revision;
    let current = true;
    if (changedWhileAway) void Promise.resolve().then(() => { if (current) void load().catch(() => {}); });
    return () => { current = false; };
  }, [active, revision, load]);
  useEffect(() => {
    if (!selectedPostId) return;
    const sequence = ++selectionRequest.current;
    const request = new AbortController(); void getPost(classroomId, selectedPostId, request.signal).then(post => { if (!request.signal.aborted && sequence === selectionRequest.current) setSelected(post); }).catch(caught => { if (!request.signal.aborted && sequence === selectionRequest.current) setError(caught); });
    return () => request.abort();
  }, [classroomId, selectedPostId]);
  async function refresh() { const sequence = selectionRequest.current; await load(); if (selected && sequence === selectionRequest.current) { try { const post = await getPost(classroomId, selected.id); if (sequence === selectionRequest.current) setSelected(post); } catch { if (sequence === selectionRequest.current) setSelected(null); } } }
  const items = page.scope === scope ? page.items : [], cursor = page.scope === scope ? page.cursor : null;
  const activeSelection = selected?.id === selectedPostId ? selected : null;
  const shown = activeSelection ? [activeSelection, ...items.filter(item => item.id !== activeSelection.id || item.kind !== activeSelection.kind)] : items;
  const error = loadError ? loadError instanceof ApiError && loadError.code === "CLASSROOM_POST_NOT_FOUND" ? ct("unavailablePost") : contentError(loadError, ct("error")) : null;
  const author = canAuthor && !archived && !admin, moderate = canModerate && !archived && !admin;
  return <section className="classroom-stream stream-layout" aria-label={ct("updates")} data-sidebar={!!classroom && !!onNavigate}>
    <div className="stream-main"><h2 className="sr-only">{ct("stream")}</h2>
      {author ? <StreamComposer classroomId={classroomId} resources={resources} sections={classwork?.sections ?? []} name={userName} initialCompose={initialCompose} request={composeRequest} onDone={refresh} onResourceDone={async () => { await Promise.all([onResourcesChanged?.(), refresh()]); }} /> : null}
      <div className="stream-toolbar"><div className="stream-filters" role="group" aria-label={tt("filters")}>{([ ["", "all"], ["ANNOUNCEMENT", "announcement"], ["ASSIGNMENT_ACTIVITY", "assignments"], ["RESOURCE_ACTIVITY", "resource"], ["DISCUSSION", "discussion"], ["PINNED", "pinned"] ] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => { setFilter(value); clearSelection(); }}>{tt(label)}</button>)}</div>
        <label className="stream-search"><SearchIcon /><span className="sr-only">{tt("search")}</span><input type="search" className="field" maxLength={200} value={query} placeholder={tt("searchPlaceholder")} onChange={event => { setQuery(event.target.value); clearSelection(); }} />{query ? <button type="button" aria-label={tt("clear")} onClick={() => { setQuery(""); setSearch(""); }}>×</button> : null}</label>
        {canInspect ? <label className="stream-status"><span className="sr-only">{ct("filter")}</span><select className="select-field" value={status} onChange={event => { setStatus(event.target.value as typeof status); clearSelection(); }}><option value="">{ct("all")}</option><option value="PUBLISHED">{ct("published")}</option><option value="DRAFT">{ct("draft")}</option><option value="ARCHIVED">{ct("archived")}</option></select></label> : null}
      </div>
      <div className="stream-feed" aria-busy={loading || query.trim() !== search}>
        {loading && !shown.length ? <div className="stream-state classroom-skeleton" role="status"><p>{ct("loading")}</p><div /><div /></div> : null}
        {error ? <div className="stream-state"><p className="notice notice-error" role="alert">{error}</p><button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void load().catch(() => {})}>{ct("retry")}</button></div> : null}
        {!loading && !error && !shown.length ? <p className="stream-state classroom-empty">{filter || status || search ? tt("noMatches") : ct("emptyFeed")}</p> : null}
        {shown.map(post => <PostCard key={`${post.kind}-${post.id}`} classroomId={classroomId} post={post} resources={resources} userId={userId} canAuthor={author} canModerate={moderate} archived={archived} admin={admin} onRefresh={refresh} onOpenAssignment={onOpenAssignment} initialComments={post.id === activeSelection?.id} />)}
      </div>
      {cursor ? <button type="button" className="btn btn-secondary stream-load-more" disabled={loading} onClick={() => void load(cursor).catch(() => {})}>{ct("loadMore")}</button> : null}
    </div>
    {classroom && onNavigate ? <StreamSidebar classroom={classroom} assignments={assignments} classwork={classwork} contentError={classworkError} members={members} canViewRoster={canViewRoster} student={student} posts={shown} onShowFeed={() => { clearSelection(); setFilter(""); setQuery(""); setSearch(""); setStatus(""); document.querySelector(".stream-toolbar")?.scrollIntoView?.({ block: "nearest" }); }} onNavigate={onNavigate} onOpenAssignment={onOpenAssignment} /> : null}
  </section>;
}
