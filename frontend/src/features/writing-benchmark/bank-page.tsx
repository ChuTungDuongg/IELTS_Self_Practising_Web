"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import * as api from "@/lib/api/writing-benchmark";
import { BuilderLifecycleProvider, useBuilderLifecycle } from "@/features/test-builder/builder-lifecycle";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { BenchmarkSampleList } from "./sample-list";
import { BenchmarkSampleEditor } from "./sample-editor";
import styles from "./bank.module.css";

type Snapshot = { rows: api.BenchmarkListItem[]; summary: api.BenchmarkSummary; selected: api.BenchmarkSample | null; task: api.BenchmarkTaskNumber };
async function snapshot(task: api.BenchmarkTaskNumber, preferred?: string): Promise<Snapshot> {
  const [rows, summary] = await Promise.all([api.listWritingBenchmarkSamples(task), api.getWritingBenchmarkSummary()]);
  const id = rows.find(row => row.id === preferred)?.id ?? rows[0]?.id;
  return { task, rows, summary, selected: id ? await api.getWritingBenchmarkSample(id) : null };
}
function listItem(sample: api.BenchmarkSample) {
  const omit = new Set(["prompt", "essay", "task1_task_type", "source_note", "redistributable"]);
  return api.benchmarkSampleListSchema.parse(Object.fromEntries(Object.entries(sample).filter(([key]) => !omit.has(key))));
}

export function WritingBenchmarkBankPage() {
  return <BuilderLifecycleProvider><BankContent /></BuilderLifecycleProvider>;
}

function BankContent() {
  const { t } = useTranslation(); const life = useBuilderLifecycle();
  const [state, setState] = useState<Snapshot | null>(null);
  const selected = useRef<api.BenchmarkSample | null>(null);
  const [error, setError] = useState(false); const [issues, setIssues] = useState<api.BenchmarkFieldIssue[]>([]);
  const [dialog, setDialog] = useState<"delete" | "image" | "reload" | null>(null);
  const [generation, setGeneration] = useState(0);
  const [reloading, setReloading] = useState(false);
  const busy = life.transitioning || life.mutating || reloading;
  const apply = useCallback((value: Snapshot) => { selected.current = value.selected; setState(value); setIssues([]); }, []);
  useEffect(() => {
    let current = true;
    void snapshot(1).then(value => { if (current) apply(value); }).catch(() => { if (current) setError(true); });
    return () => { current = false; };
  }, [apply]);
  const ack = useCallback((saved: api.BenchmarkSample) => {
    if (selected.current?.id !== saved.id) return;
    selected.current = saved;
    setState(previous => previous ? { ...previous, selected: saved, rows: previous.rows.map(row => row.id === saved.id ? listItem(saved) : row) } : previous);
    void api.getWritingBenchmarkSummary().then(summary => setState(previous => previous ? { ...previous, summary } : previous)).catch(() => undefined);
  }, []);
  async function transition(action: () => Promise<void>) {
    setError(false); setIssues([]);
    try { return (await life.runTransition(() => life.runMutation(action))).ready; }
    catch (failure) { setIssues(api.benchmarkCompletionIssues(failure)); setError(true); return false; }
  }
  function choose(id: string) {
    void transition(async () => { const saved = await api.getWritingBenchmarkSample(id); selected.current = saved; setState(previous => previous ? { ...previous, selected: saved } : previous); });
  }
  async function complete(next = false) {
    await transition(async () => {
      const current = selected.current; if (!current) return;
      const saved = await api.completeWritingBenchmarkSample(current.id, current.revision); ack(saved);
      const rows = await api.listWritingBenchmarkSamples(current.task_number);
      const incomplete = rows.filter(row => row.id !== current.id && row.status === "DRAFT");
      const nextId = next ? (incomplete.find(row => row.sequence_number > current.sequence_number) ?? incomplete[0])?.id : undefined;
      apply(await snapshot(current.task_number, nextId ?? saved.id));
    });
  }
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.repeat || dialog || busy) return;
      if (event.key.toLowerCase() === "s") { event.preventDefault(); void life.flushAutosaves(); }
      if (event.key === "Enter") { event.preventDefault(); void complete(true); }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });
  async function confirm() {
    if (dialog === "reload") {
      // Explicit discard is the only transition allowed around a conflict barrier.
      setError(false); setReloading(true);
      try { if (selected.current) { const saved = await api.getWritingBenchmarkSample(selected.current.id); selected.current = saved; setState(previous => previous ? { ...previous, selected: saved } : previous); setGeneration(value => value + 1); setDialog(null); } }
      catch { setError(true); }
      finally { setReloading(false); }
      return;
    }
    const success = await transition(async () => {
      const current = selected.current; if (!current) return;
      if (dialog === "image") ack(await api.removeWritingBenchmarkImage(current.id, current.revision));
      else { await api.deleteWritingBenchmarkSample(current.id, current.revision); apply(await snapshot(current.task_number)); }
    });
    if (success) setDialog(null);
  }
  const status = { SAVED: "common.saved", DIRTY: "benchmark.unsaved", SAVING: "common.saving", ERROR: "benchmark.saveFailed", INVALID: "benchmark.saveFailed", CONFLICT: "benchmark.conflict" } as const;
  return <>
    <PageHeading eyebrow={t("admin.administration")} title={t("benchmark.title")} description={t("benchmark.description")} />
    <div className={styles.actions}><span role="status" aria-live="polite">{t(status[life.autosaveState])}</span>{life.autosaveState === "ERROR" || life.autosaveState === "DIRTY" ? <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => void life.flushAutosaves()}>{t("common.retry")}</button> : null}{life.autosaveState === "CONFLICT" ? <button className="btn btn-ghost" type="button" onClick={() => setDialog("reload")}>{t("benchmark.reload")}</button> : null}</div>
    {error ? <p role="alert" className="notice notice-error">{t(issues.length ? "benchmark.incomplete" : "benchmark.operationFailed")}</p> : null}
    {!state ? <p className="notice">{t("benchmark.loading")}</p> : <>
      <div role="tablist" aria-label={t("benchmark.tasks")} className={styles.actions}>{state.summary.tasks.map(task => <button key={task.task_number} id={`benchmark-tab-${task.task_number}`} role="tab" type="button" aria-selected={state.task === task.task_number} aria-controls="benchmark-task-panel" tabIndex={state.task === task.task_number ? 0 : -1} className="btn btn-secondary" disabled={busy} onClick={() => void transition(async () => apply(await snapshot(task.task_number)))} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); const other = state.task === 1 ? 2 : 1; void transition(async () => { apply(await snapshot(other)); document.getElementById(`benchmark-tab-${other}`)?.focus(); }); } }}>{t("benchmark.task", { number: task.task_number })} · {t("benchmark.progress", { count: task.complete })}</button>)}</div>
      <div id="benchmark-task-panel" role="tabpanel" aria-labelledby={`benchmark-tab-${state.task}`} className={styles.layout}>
        <BenchmarkSampleList rows={state.rows} selectedId={state.selected?.id} disabled={busy} full={(state.summary.tasks.find(task => task.task_number === state.task)?.total ?? 0) >= 100} onSelect={choose} onCreate={() => void transition(async () => { const saved = await api.createWritingBenchmarkSample(state.task); apply(await snapshot(state.task, saved.id)); })} />
        {state.selected ? <BenchmarkSampleEditor key={`${state.selected.id}:${generation}`} sample={state.selected} disabled={busy} issues={issues} onSaved={ack} onEdit={() => setIssues([])} onComplete={() => void complete()} onDelete={() => setDialog("delete")} onRemove={() => setDialog("image")} onUpload={file => transition(async () => { const current = selected.current; if (current) ack(await api.uploadWritingBenchmarkImage(current.id, file, current.revision)); })} /> : <section className="surface-card"><p className="notice">{t("benchmark.selectSample")}</p></section>}
      </div>
    </>}
    <ConfirmDialog open={dialog !== null} title={t(dialog === "image" ? "benchmark.removeImage" : dialog === "reload" ? "benchmark.reload" : "benchmark.delete")} description={t(dialog === "image" ? "benchmark.removeImageConfirm" : dialog === "reload" ? "benchmark.reloadConfirm" : "benchmark.deleteConfirm")} confirmLabel={t(dialog === "image" ? "benchmark.removeImage" : dialog === "reload" ? "benchmark.reload" : "benchmark.delete")} pending={busy} errorMessage={error ? t("benchmark.operationFailed") : undefined} onCancel={() => setDialog(null)} onConfirm={() => void confirm()} />
  </>;
}
