"use client";

import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api/writing-anchors";
import { AnchorForm } from "./anchor-form";
import { AnchorCoveragePanel } from "./anchor-coverage";
import { bankLabels } from "./anchor-presentation";
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
  const draft = sets.find(s => s.status === "DRAFT");
  const writable = selected?.status === "DRAFT";
  useEffect(() => {
    let current = true;
    api.listAnchorSets().then(data => {
      if (!current) return;
      setSets(data.items); setLoading(false);
      setSetId(old => data.items.some(s => s.id === old) ? old : data.items.find(s => s.status === "DRAFT")?.id ?? data.items[0]?.id ?? "");
    }).catch(e => { if (current) { setError(e instanceof Error ? e.message : "Không thể tải bộ dữ liệu anchor. Hãy làm mới để thử lại."); setLoading(false); } });
    api.getAnchorCoverage().then(data => {
      if (current) { setCoverage(data); setCoverageLoading(false); }
    }).catch(e => { if (current) { setCoverage(null); setCoverageLoading(false); setError(e instanceof Error ? e.message : "Không thể tải mức độ sẵn sàng của anchor. Hãy làm mới để thử lại."); } });
    return () => { current = false; };
  }, [revision]);
  useEffect(() => {
    let current = true;
    if (setId) api.listAnchors({ set_id: setId, search, task_number: number ? Number(number) : undefined, task_type: type, writing_task_id: taskId, status, offset }).then(data => { if (current) setPage(data); }).catch(e => { if (current) setError(e instanceof Error ? e.message : "Không thể tải bài tham chiếu. Hãy làm mới để thử lại."); });
    return () => { current = false; };
  }, [setId, search, number, type, taskId, status, offset, revision]);
  function close() { detailEpoch.current++; setForm(null); }
  function choose(id: string) { close(); setSetId(id); setPage(null); setOffset(0); setTaskId(""); }
  function addToDraft() {
    if (!draft || busy || loading) return;
    if (draft.id !== setId) choose(draft.id);
    else close();
    setForm({ detail: null, key: ++detailEpoch.current });
  }
  function refresh() {
    close(); setCoverage(null); setCoverageLoading(true); setPage(null); setLoading(true);
    setRevision(v => v + 1);
  }
  async function mutate(work: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await work(); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Không thể lưu thay đổi. Hãy làm mới bộ dữ liệu rồi thử lại."); }
    finally { setBusy(false); }
  }
  async function view(id: string) {
    const epoch = ++detailEpoch.current; setError("");
    try { const detail = await api.getAnchor(id); if (epoch === detailEpoch.current) setForm({ detail, key: epoch }); }
    catch (e) { if (epoch === detailEpoch.current) setError(e instanceof Error ? e.message : "Không thể mở bài tham chiếu. Hãy thử lại."); }
  }
  return <div className={styles.workspace} lang="vi">
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <section className={`surface-card ${styles.panel}`} aria-label="Bộ dữ liệu anchor">
      <div className={styles.heading}>
        <div><h2>Bộ dữ liệu anchor</h2>{selected && <p className={styles.versionTitle}>{bankLabels[selected.status]}{selected.status === "ACTIVE" ? ":" : ""} v{selected.version} <span className={styles.badge}>{writable ? "Đang chỉnh sửa" : "Chỉ đọc"}</span></p>}</div>
        <p className={styles.activeBank}>Bộ anchor đang dùng: <strong>{coverage ? coverage.active_set ? `v${coverage.active_set.version}` : "Chưa có" : coverageLoading ? "Đang tải…" : "Chưa xác định"}</strong></p>
      </div>
      <p className={styles.help}>Chỉ bản nháp mới có thể chỉnh sửa. Khi kích hoạt, bản này sẽ trở thành bộ dữ liệu đang dùng và phiên bản cũ được lưu lại.</p>
      {loading ? <p role="status">Đang tải bộ dữ liệu anchor…</p> : !sets.length ? <p>Chưa có bộ dữ liệu anchor. Tạo bản nháp để bắt đầu.</p> : null}
      <div className={styles.actions}><label className={styles.versionSelect}>Phiên bản<select value={setId} disabled={busy} onChange={e => choose(e.target.value)}><option value="">Chọn phiên bản</option>{sets.map(s => <option value={s.id} key={s.id}>v{s.version} · {bankLabels[s.status]} · {s.name}</option>)}</select></label>
      {!draft && <button className="btn btn-primary" disabled={loading || busy} onClick={() => mutate(async () => { const draft = await api.createAnchorDraft(); setSets(old => [...old, draft]); setSetId(draft.id); })}>{sets.some(s => s.status === "ACTIVE") ? "Tạo bản nháp mới từ bản đang dùng" : "Tạo bản nháp"}</button>}
      {writable && <><button className="btn btn-primary" disabled={busy || loading} onClick={addToDraft}>Thêm bài tham chiếu</button><button className="btn btn-secondary" disabled={busy || loading} onClick={() => mutate(async () => {
        const activated = await api.activateAnchorSet(setId);
        setSets(old => old.map(s => s.id === activated.id ? activated : s.status === "ACTIVE" ? { ...s, status: "RETIRED" } : s));
      })}>Kích hoạt bản nháp</button></>}
      <button className="btn btn-ghost" disabled={busy} onClick={() => { setError(""); refresh(); }}>Làm mới</button></div>
      {selected && !writable && <p className={styles.help}>Phiên bản này chỉ đọc. Tạo hoặc chọn bản nháp để chỉnh sửa.</p>}
    </section>
    {form && selected && <section className={`surface-card ${styles.panel}`}><AnchorForm key={`${setId}:${form.key}:${selected.status}`} detail={form.detail} readOnly={!writable} busy={busy} onCancel={close} onSave={input => mutate(() => form.detail ? api.updateAnchor(form.detail.id, input) : api.createAnchor(setId, input))} /></section>}
    {selected && <section className={`surface-card ${styles.panel}`} aria-label="Các bài tham chiếu"><h2>Các bài tham chiếu · v{selected.version}</h2>
      <div className={styles.filters}>
        <label>Tìm bài tham chiếu<input maxLength={160} value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} /></label>
        <label>Kỹ năng<select value={number} onChange={e => { setNumber(e.target.value); setOffset(0); }}><option value="">Cả Task 1 và Task 2</option><option value="1">Task 1</option><option value="2">Task 2</option></select></label>
        <label>Dạng bài<input maxLength={64} value={type} onChange={e => { setType(e.target.value); setOffset(0); }} /></label>
        <label>Trạng thái<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">Tất cả</option>{(["DRAFT","ACTIVE","RETIRED"] as const).map(s => <option key={s} value={s}>{bankLabels[s]}</option>)}</select></label>
        <label>Đề Writing<select value={taskId} onChange={e => { setTaskId(e.target.value); setOffset(0); }}><option value="">Tất cả đề</option>{Array.from(new Map(page?.items.map(a => [a.task.id, a.task])).values()).map(t => <option key={t.id} value={t.id}>{t.test_title} · v{t.version_number} · Task {t.task_number}</option>)}</select></label>
      </div>
      <div className={styles.overflow}><table><thead><tr><th>Đề Writing</th><th>Số từ</th><th>TA / TR</th><th>CC</th><th>LR</th><th>GRA</th><th>Ngày thêm</th><th>Thao tác</th></tr></thead><tbody>{page?.items.map(a => <tr key={a.id}><td>{a.task.test_title} · v{a.task.version_number} · Task {a.task.task_number}<small>{a.task.task_type} · {a.task.prompt_preview}</small></td><td>{a.word_count}</td>{(["ta","cc","lr","gra"] as const).map(t => <td key={t}>{a.human_scores[t].toFixed(1)}</td>)}<td><time dateTime={a.created_at}>{a.created_at.slice(0, 10)}</time></td><td><div className={styles.rowActions}><button className="btn btn-secondary" disabled={busy || loading} onClick={() => view(a.id)}>{writable ? "Xem / chỉnh sửa" : "Xem"}</button>{writable && <button className="btn btn-ghost" disabled={busy || loading} onClick={() => mutate(() => api.deleteAnchor(a.id))}>Xóa</button>}</div></td></tr>)}</tbody></table></div>
      {page?.total === 0 && <div className={styles.emptyState}><p>Chưa có bài tham chiếu phù hợp với bộ lọc hiện tại.</p>{writable && !search && !number && !type && !status && !taskId && <p className={styles.help}>Hãy thêm các bài Writing đã được chấm thủ công để bắt đầu xây dựng bộ anchor.</p>}</div>}
      <nav className={styles.pagination} aria-label="Phân trang bài tham chiếu"><button className="btn btn-secondary" disabled={busy || !offset} onClick={() => setOffset(v => Math.max(0, v - 25))}>Trước</button><span>{page?.total ?? 0} bài</span><button className="btn btn-secondary" disabled={busy || !page || offset + page.limit >= page.total} onClick={() => setOffset(v => v + 25)}>Sau</button></nav>
    </section>}
    <AnchorCoveragePanel coverage={coverage} loading={coverageLoading} onAddAnchor={draft ? addToDraft : undefined} busy={busy || loading} />
  </div>;
}
