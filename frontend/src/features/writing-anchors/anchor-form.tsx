"use client";

import { useEffect, useState } from "react";
import { anchorInputSchema, listFrozenTasks, type AnchorDetail, type AnchorInput, type FrozenTask } from "@/lib/api/writing-anchors";
import { criterionNames } from "./anchor-presentation";
import styles from "./anchor-workspace.module.css";

const traits = ["ta", "cc", "lr", "gra"] as const;

export function AnchorForm({ detail, readOnly, busy, onSave, onCancel }: { detail: AnchorDetail | null; readOnly: boolean; busy: boolean; onSave: (input: AnchorInput) => Promise<void>; onCancel: () => void }) {
  const [selected, setSelected] = useState<FrozenTask | null>(detail?.task ?? null);
  const [tasks, setTasks] = useState<FrozenTask[]>([]);
  const [search, setSearch] = useState("");
  const [number, setNumber] = useState("");
  const [response, setResponse] = useState(detail?.response_text ?? "");
  const [scores, setScores] = useState(() => ({ ta: String(detail?.human_scores.ta ?? 7), cc: String(detail?.human_scores.cc ?? 7), lr: String(detail?.human_scores.lr ?? 7), gra: String(detail?.human_scores.gra ?? 7) }));
  const [note, setNote] = useState(detail?.admin_note ?? "");
  const [provenance, setProvenance] = useState(detail?.provenance ?? "");
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    listFrozenTasks({ search, task_number: number ? Number(number) : undefined, limit: 100 }).then(data => { if (current) setTasks(data.items); }).catch(e => { if (current) setError(e instanceof Error ? e.message : "Không thể tải đề Writing. Hãy thử lại."); });
    return () => { current = false; };
  }, [search, number]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError("");
    if (!selected) { setError("Vui lòng chọn đề Writing đã xuất bản."); return; }
    if (!response.trim()) { setError("Vui lòng nhập bài viết của học viên (không chỉ khoảng trắng)."); return; }
    const humanScores = Object.fromEntries(traits.map(trait => [trait, scores[trait].trim() ? Number(scores[trait]) : NaN]));
    const parsed = anchorInputSchema.safeParse({ writing_task_id: selected.id, response_text: response, human_scores: humanScores, admin_note: note || null, provenance: provenance || null });
    if (!parsed.success) { setError("Vui lòng chọn đề Writing, nhập bài viết và đủ 4 điểm tiêu chí hợp lệ theo bước 0.5 từ 0 đến 9."); return; }
    await onSave(parsed.data);
  }
  const options = selected && !tasks.some(t => t.id === selected.id) ? [selected, ...tasks] : tasks;
  return <form className={styles.form} onSubmit={submit} noValidate aria-label="Biểu mẫu bài tham chiếu">
    <h2>{readOnly ? "Xem bài tham chiếu" : detail ? "Chỉnh sửa bài tham chiếu" : "Thêm bài tham chiếu"}</h2>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <fieldset disabled={readOnly || busy}><legend>Đề Writing và điểm chấm thủ công</legend>
      <div className={styles.formFilters}>
        <label>Tìm đề Writing<input value={search} onChange={e => setSearch(e.target.value)} maxLength={160} /></label>
        <label>Task<select value={number} onChange={e => setNumber(e.target.value)}><option value="">Cả hai</option><option value="1">Task 1</option><option value="2">Task 2</option></select></label>
      </div>
      <label>Đề Writing đã xuất bản<select required value={selected?.id ?? ""} onChange={e => setSelected(options.find(t => t.id === e.target.value) ?? null)}><option value="">Chọn đề Writing</option>{options.map(t => <option key={t.id} value={t.id}>{t.test_title} · v{t.version_number} · Task {t.task_number} · {t.task_type ?? "Khác"} · {t.prompt_preview}</option>)}</select></label>
      {selected && <p className={styles.help}>{selected.prompt_preview}</p>}
      <label>Bài viết của học viên<textarea rows={12} required value={response} onChange={e => setResponse(e.target.value)} maxLength={100000} /></label>
      <div className={styles.scores}>{traits.map(t => {
        const label = t === "ta" ? selected?.task_number === 2 ? "Task Response (TR)" : "Task Achievement (TA)" : t.toUpperCase();
        return <label key={t}><span>{label}</span>{t !== "ta" && <small id={`anchor-${t}-name`}>{criterionNames[t]}</small>}<input aria-label={label} aria-describedby={t !== "ta" ? `anchor-${t}-name` : undefined} type="number" required min={0} max={9} step={0.5} value={scores[t]} onChange={e => setScores(s => ({ ...s, [t]: e.target.value }))} /></label>;
      })}</div>
      <p className={styles.help}>Nhập đủ 4 điểm tiêu chí từ 0 đến 9, theo bước 0.5.</p>
      <label>Ghi chú nội bộ<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} /></label>
      <label>Nguồn / xuất xứ<input value={provenance} onChange={e => setProvenance(e.target.value)} maxLength={2000} /></label>
    </fieldset>
    <div className={styles.actions}>{!readOnly && <button className="btn btn-primary" disabled={busy} type="submit">Lưu bài tham chiếu</button>}<button className="btn btn-secondary" type="button" disabled={busy} onClick={onCancel}>{readOnly ? "Đóng" : "Hủy"}</button></div>
  </form>;
}
