"use client";

import { useEffect, useState } from "react";
import { anchorInputSchema, listFrozenTasks, type AnchorDetail, type AnchorInput, type FrozenTask } from "@/lib/api/writing-anchors";
import styles from "./anchor-workspace.module.css";

export function AnchorForm({ detail, readOnly, busy, onSave, onCancel }: { detail: AnchorDetail | null; readOnly: boolean; busy: boolean; onSave: (input: AnchorInput) => Promise<void>; onCancel: () => void }) {
  const [selected, setSelected] = useState<FrozenTask | null>(detail?.task ?? null);
  const [tasks, setTasks] = useState<FrozenTask[]>([]);
  const [search, setSearch] = useState("");
  const [number, setNumber] = useState("");
  const [response, setResponse] = useState(detail?.response_text ?? "");
  const [scores, setScores] = useState(detail?.human_scores ?? { ta: 7, cc: 7, lr: 7, gra: 7 });
  const [note, setNote] = useState(detail?.admin_note ?? "");
  const [provenance, setProvenance] = useState(detail?.provenance ?? "");
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    listFrozenTasks({ search, task_number: number ? Number(number) : undefined, limit: 100 }).then(data => { if (current) setTasks(data.items); }).catch(e => { if (current) setError(e instanceof Error ? e.message : "Tasks unavailable."); });
    return () => { current = false; };
  }, [search, number]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError("");
    const parsed = anchorInputSchema.safeParse({ writing_task_id: selected?.id, response_text: response, human_scores: scores, admin_note: note || null, provenance: provenance || null });
    if (!parsed.success) { setError("Select a frozen task, enter a response and four valid half-band scores (0–9)."); return; }
    await onSave(parsed.data);
  }
  const options = selected && !tasks.some(t => t.id === selected.id) ? [selected, ...tasks] : tasks;
  return <form className={styles.form} onSubmit={submit} aria-label="Human anchor form">
    <h2>{readOnly ? "View anchor" : detail ? "Edit anchor" : "Add human anchor"}</h2>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={readOnly || busy}><legend>Frozen task and human labels</legend>
      <label>Search frozen tasks<input value={search} onChange={e => setSearch(e.target.value)} maxLength={160} /></label>
      <label>Task number<select value={number} onChange={e => setNumber(e.target.value)}><option value="">Both</option><option value="1">Task 1</option><option value="2">Task 2</option></select></label>
      <label>Frozen Writing task<select required value={selected?.id ?? ""} onChange={e => setSelected(options.find(t => t.id === e.target.value) ?? null)}><option value="">Select a published task</option>{options.map(t => <option key={t.id} value={t.id}>{t.test_title} · v{t.version_number} · Task {t.task_number} · {t.task_type ?? "Other"} · {t.prompt_preview}</option>)}</select></label>
      {selected && <p>{selected.prompt_preview}</p>}
      <label>Response text<textarea rows={12} required value={response} onChange={e => setResponse(e.target.value)} maxLength={100000} /></label>
      <div className={styles.scores}>{(["ta","cc","lr","gra"] as const).map(t => <label key={t}>{t === "ta" ? selected?.task_number === 2 ? "Task Response (TR)" : "Task Achievement (TA)" : t.toUpperCase()}<input type="number" required min={0} max={9} step={0.5} value={scores[t]} onChange={e => setScores(s => ({ ...s, [t]: Number(e.target.value) }))} /></label>)}</div>
      <label>Private admin note<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} /></label>
      <label>Private provenance<input value={provenance} onChange={e => setProvenance(e.target.value)} maxLength={2000} /></label>
    </fieldset>
    <div className={styles.actions}>{!readOnly && <button className="btn btn-primary" disabled={busy} type="submit">Save anchor</button>}<button className="btn btn-secondary" type="button" disabled={busy} onClick={onCancel}>{readOnly ? "Close" : "Cancel"}</button></div>
  </form>;
}
