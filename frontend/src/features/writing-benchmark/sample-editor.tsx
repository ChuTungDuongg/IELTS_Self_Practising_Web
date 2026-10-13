import { useLayoutEffect, useRef, useState } from "react";
import { benchmarkTaskTypes, updateWritingBenchmarkSample, type BenchmarkSample, type BenchmarkPatch, type BenchmarkFieldIssue } from "@/lib/api/writing-benchmark";
import { useBuilderAutosave } from "@/features/test-builder/builder-lifecycle";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { BenchmarkImageField } from "./image-field";
import styles from "./bank.module.css";

type Draft = { prompt: string; essay: string; split: "DEV" | "HOLDOUT"; task1_task_type: BenchmarkSample["task1_task_type"]; source_note: string | null; redistributable: boolean; human_scores: NonNullable<BenchmarkPatch["human_scores"]> };
function editable(sample: BenchmarkSample): Draft {
  return { prompt: sample.prompt, essay: sample.essay, split: sample.split, task1_task_type: sample.task1_task_type, source_note: sample.source_note, redistributable: sample.redistributable, human_scores: { ...sample.human_scores } };
}

export function BenchmarkSampleEditor({ sample, disabled, issues, onSaved, onEdit, onComplete, onDelete, onUpload, onRemove }: {
  sample: BenchmarkSample; disabled: boolean; issues: BenchmarkFieldIssue[]; onSaved: (sample: BenchmarkSample) => void; onEdit: () => void;
  onComplete: () => void; onDelete: () => void; onUpload: (file: File) => Promise<boolean>; onRemove: () => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(() => editable(sample));
  const revision = useRef(sample.revision);
  useLayoutEffect(() => { revision.current = sample.revision; }, [sample.revision]);
  const autosave = useBuilderAutosave({ resourceKey: `writing-benchmark:${sample.id}`, value: draft, delay: 1000,
    save: async (value: Draft) => {
      const { task1_task_type, ...fields } = value;
      return updateWritingBenchmarkSample(sample.id, { ...fields, ...(sample.task_number === 1 ? { task1_task_type } : {}), expected_revision: revision.current });
    },
    onSaved: (saved, _submitted, unchanged) => {
      revision.current = saved.revision; onSaved(saved);
      if (unchanged) { const canonical = editable(saved); setDraft(canonical); return canonical; }
    },
  });
  function change(edits: Partial<Draft>) {
    const next = { ...draft, ...edits }; setDraft(next); autosave.stageValue(next, true); onEdit();
  }
  const first = sample.task_number === 1 ? "ta" : "tr";
  const criteria = [first, "cc", "lr", "gra"] as const;
  const labels = { ta: "benchmark.ta", tr: "benchmark.tr", cc: "benchmark.cc", lr: "benchmark.lr", gra: "benchmark.gra" } as const;
  const values = criteria.map(trait => draft.human_scores[trait]);
  const overall = values.every((value): value is number => typeof value === "number") ? Math.floor((values as number[]).reduce((sum, value) => sum + value, 0) / 4 * 2 + .5) / 2 : null;
  const invalid = (field: string) => issues.some(issue => issue.path === field);
  function fieldError(field: string) { return invalid(field) ? <small id={`${sample.id}-${field}`} role="alert">{t("benchmark.required")}</small> : null; }
  return <section className={`surface-card ${styles.editor}`} aria-label={t("benchmark.selected")}>
    <div className={styles.actions}><h2 className="section-title">{sample.code}</h2><span>{t(sample.status === "COMPLETE" ? "benchmark.completeStatus" : "benchmark.draft")}</span></div>
    <fieldset disabled={disabled} className={styles.fields}>
      {sample.task_number === 1 ? <label className={styles.field}>{t("benchmark.taskType")}<select aria-label={t("benchmark.taskType")} aria-describedby={invalid("task1_task_type") ? `${sample.id}-task1_task_type` : undefined} className="select-field" value={draft.task1_task_type ?? ""} aria-invalid={invalid("task1_task_type")} onChange={event => change({ task1_task_type: event.target.value ? event.target.value as BenchmarkSample["task1_task_type"] : null })}><option value="">{t("benchmark.chooseType")}</option>{benchmarkTaskTypes.map(type => <option key={type} value={type}>{t(`benchmark.type.${type}`)}</option>)}</select>{fieldError("task1_task_type")}</label> : null}
      <label className={styles.field}>{t("benchmark.prompt")}<textarea aria-label={t("benchmark.prompt")} aria-describedby={invalid("prompt") ? `${sample.id}-prompt` : undefined} className="textarea-field" value={draft.prompt} maxLength={20000} aria-invalid={invalid("prompt")} onChange={event => change({ prompt: event.target.value })} />{fieldError("prompt")}</label>
      {sample.task_number === 1 ? <><BenchmarkImageField sample={sample} disabled={disabled} onUpload={onUpload} onRemove={onRemove} />{fieldError("image")}</> : null}
      <label className={styles.field}>{t("benchmark.essay")}<textarea aria-label={t("benchmark.essay")} aria-describedby={invalid("essay") ? `${sample.id}-essay` : undefined} className="textarea-field" value={draft.essay} maxLength={100000} aria-invalid={invalid("essay")} onChange={event => change({ essay: event.target.value })} />{fieldError("essay")}</label>
      <div className={styles.criteria}>{criteria.map(trait => <label key={trait} className={styles.field}>{t(labels[trait])}<select aria-label={t(labels[trait])} aria-describedby={invalid(`human_scores.${trait}`) ? `${sample.id}-human_scores.${trait}` : undefined} className="select-field" value={draft.human_scores[trait] ?? ""} aria-invalid={invalid(`human_scores.${trait}`)} onChange={event => change({ human_scores: { ...draft.human_scores, [trait]: event.target.value === "" ? null : Number(event.target.value) } })}><option value="">{t("benchmark.chooseScore")}</option>{Array.from({ length: 19 }, (_, i) => <option key={i} value={i / 2}>{(i / 2).toFixed(1)}</option>)}</select>{fieldError(`human_scores.${trait}`)}</label>)}</div>
      <output aria-label={t("benchmark.overall")}>{t("benchmark.overall")}: <strong>{overall?.toFixed(1) ?? "—"}</strong></output>
      <label className={styles.field}>{t("benchmark.split")}<select className="select-field" value={draft.split} onChange={event => change({ split: event.target.value as Draft["split"] })}><option value="DEV">{t("benchmark.dev")}</option><option value="HOLDOUT">{t("benchmark.holdout")}</option></select></label>
      <label className={styles.field}>{t("benchmark.source")}<textarea className="textarea-field" maxLength={2000} value={draft.source_note ?? ""} onChange={event => change({ source_note: event.target.value || null })} /></label>
      <label><input type="checkbox" checked={draft.redistributable} onChange={event => change({ redistributable: event.target.checked })} /> {t("benchmark.redistributable")}</label>
    </fieldset>
    <div className={styles.actions}><button type="button" className="btn btn-primary" disabled={disabled} onClick={onComplete}>{t("benchmark.complete")}</button><button type="button" className="btn btn-ghost" disabled={disabled} onClick={onDelete}>{t("benchmark.delete")}</button></div>
  </section>;
}
