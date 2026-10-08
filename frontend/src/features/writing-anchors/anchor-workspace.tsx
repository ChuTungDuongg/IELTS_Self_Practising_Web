"use client";

import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api/writing-anchors";
import { AnchorForm } from "./anchor-form";
import { AnchorCoveragePanel } from "./anchor-coverage";
import styles from "./anchor-workspace.module.css";

export function AnchorWorkspace() {
  const [sets, setSets] = useState<api.AnchorSet[]>([]);
  const [setId, setSetId] = useState("");
  const [coverage, setCoverage] = useState<api.AnchorCoverage | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(true);
  const [page, setPage] = useState<api.AnchorPage | null>(null);
  const [search, setSearch] = useState("");
  const [number, setNumber] = useState("");
  const [type, setType] = useState("");
  const [taskId, setTaskId] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<{ detail: api.AnchorDetail | null; key: number } | null>(null);
  const detailEpoch = useRef(0);
  const selected = sets.find(s => s.id === setId);
  const writable = selected?.status === "DRAFT";
  useEffect(() => {
    let current = true;
    api.listAnchorSets().then(data => {
      if (!current) return;
      setSets(data.items); setLoading(false);
      setSetId(old => data.items.some(s => s.id === old) ? old : data.items.find(s => s.status === "DRAFT")?.id ?? data.items[0]?.id ?? "");
    }).catch(e => { if (current) { setError(e instanceof Error ? e.message : "Workspace unavailable."); setLoading(false); } });
    api.getAnchorCoverage().then(data => {
      if (current) { setCoverage(data); setCoverageLoading(false); }
    }).catch(e => { if (current) { setCoverage(null); setCoverageLoading(false); setError(e instanceof Error ? e.message : "Active coverage unavailable."); } });
    return () => { current = false; };
  }, [revision]);
  useEffect(() => {
    let current = true;
    if (setId) api.listAnchors({ set_id: setId, search, task_number: number ? Number(number) : undefined, task_type: type, writing_task_id: taskId, status, offset }).then(data => { if (current) setPage(data); }).catch(e => { if (current) setError(e instanceof Error ? e.message : "Anchors unavailable."); });
    return () => { current = false; };
  }, [setId, search, number, type, taskId, status, offset, revision]);
  function close() { detailEpoch.current++; setForm(null); }
  function choose(id: string) { close(); setSetId(id); setPage(null); setOffset(0); setTaskId(""); }
  function refresh() {
    close(); setCoverage(null); setCoverageLoading(true); setPage(null); setLoading(true);
    setRevision(v => v + 1);
  }
  async function mutate(work: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await work(); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Change failed; reload the bank."); }
    finally { setBusy(false); }
  }
  async function view(id: string) {
    const epoch = ++detailEpoch.current; setError("");
    try { const detail = await api.getAnchor(id); if (epoch === detailEpoch.current) setForm({ detail, key: epoch }); }
    catch (e) { if (epoch === detailEpoch.current) setError(e instanceof Error ? e.message : "Anchor unavailable."); }
  }
  return <div className={styles.workspace}>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <section className={`surface-card ${styles.panel}`} aria-label="Anchor versions">
      <h2>Versioned human bank</h2><p>Only a draft is editable. Activation freezes its content and retires the previous active version.</p>
      {loading ? <p role="status">Loading anchor sets…</p> : !sets.length ? <p>No anchor sets yet.</p> : null}
      <div className={styles.actions}><label>Anchor set<select value={setId} disabled={busy} onChange={e => choose(e.target.value)}><option value="">Select a set</option>{sets.map(s => <option value={s.id} key={s.id}>{s.name} · v{s.version} · {s.status}</option>)}</select></label>
      {!sets.some(s => s.status === "DRAFT") && <button className="btn btn-primary" disabled={loading || busy} onClick={() => mutate(async () => { const draft = await api.createAnchorDraft(); setSets(old => [...old, draft]); setSetId(draft.id); })}>{sets.some(s => s.status === "ACTIVE") ? "Clone active to draft" : "Create draft"}</button>}
      {writable && <><button className="btn btn-secondary" disabled={busy || loading} onClick={() => { close(); setForm({ detail: null, key: ++detailEpoch.current }); }}>Add anchor</button><button className="btn btn-primary" disabled={busy || loading} onClick={() => mutate(async () => {
        const activated = await api.activateAnchorSet(setId);
        setSets(old => old.map(s => s.id === activated.id ? activated : s.status === "ACTIVE" ? { ...s, status: "RETIRED" } : s));
      })}>Activate draft</button></>}
      <button className="btn btn-secondary" disabled={busy} onClick={() => { setError(""); refresh(); }}>Refresh</button></div>
      {selected && !writable && <p>Read-only {selected.status.toLowerCase()} version. Create or select a draft to edit.</p>}
    </section>
    {form && selected && <section className={`surface-card ${styles.panel}`}><AnchorForm key={`${setId}:${form.key}:${selected.status}`} detail={form.detail} readOnly={!writable} busy={busy} onCancel={close} onSave={input => mutate(() => form.detail ? api.updateAnchor(form.detail.id, input) : api.createAnchor(setId, input))} /></section>}
    {selected && <section className={`surface-card ${styles.panel}`} aria-label="Anchor list"><h2>Responses · v{selected.version}</h2>
      <div className={styles.filters}><label>Search anchors<input maxLength={160} value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} /></label><label>Task filter<select value={number} onChange={e => { setNumber(e.target.value); setOffset(0); }}><option value="">Both tasks</option><option value="1">Task 1</option><option value="2">Task 2</option></select></label><label>Task type<input maxLength={64} value={type} onChange={e => { setType(e.target.value); setOffset(0); }} /></label><label>Status filter<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">All</option>{["DRAFT","ACTIVE","RETIRED"].map(s => <option key={s}>{s}</option>)}</select></label><label>Frozen task filter<select value={taskId} onChange={e => { setTaskId(e.target.value); setOffset(0); }}><option value="">All tasks</option>{Array.from(new Map(page?.items.map(a => [a.task.id, a.task])).values()).map(t => <option key={t.id} value={t.id}>{t.test_title} · v{t.version_number} · Task {t.task_number}</option>)}</select></label></div>
      <div className={styles.overflow}><table><thead><tr><th>Frozen task</th><th>Words</th><th>TA / TR</th><th>CC</th><th>LR</th><th>GRA</th><th>Created</th><th>Actions</th></tr></thead><tbody>{page?.items.map(a => <tr key={a.id}><td>{a.task.test_title} · v{a.task.version_number} · Task {a.task.task_number}<small>{a.task.task_type} · {a.task.prompt_preview}</small></td><td>{a.word_count}</td>{(["ta","cc","lr","gra"] as const).map(t => <td key={t}>{a.human_scores[t].toFixed(1)}</td>)}<td><time dateTime={a.created_at}>{a.created_at.slice(0, 10)}</time></td><td><button className="btn btn-secondary" disabled={busy || loading} onClick={() => view(a.id)}>{writable ? "View / edit" : "View"}</button>{writable && <button className="btn btn-secondary" disabled={busy || loading} onClick={() => mutate(() => api.deleteAnchor(a.id))}>Delete</button>}</td></tr>)}</tbody></table></div>
      {page?.total === 0 && <p>No anchors match these filters.</p>}
      <div className={styles.actions}><button disabled={busy || !offset} onClick={() => setOffset(v => Math.max(0, v - 25))}>Previous</button><span>{page?.total ?? 0} anchors</span><button disabled={busy || !page || offset + page.limit >= page.total} onClick={() => setOffset(v => v + 25)}>Next</button></div>
    </section>}
    <AnchorCoveragePanel coverage={coverage} loading={coverageLoading} />
  </div>;
}
