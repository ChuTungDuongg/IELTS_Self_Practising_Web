"use client";

import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api/writing-anchors";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { AnchorForm } from "./anchor-form";
import { AnchorCoveragePanel } from "./anchor-coverage";
import { anchorTaskLabel } from "./anchor-presentation";
import styles from "./anchor-workspace.module.css";

type Confirmation = { kind: "bank" | "cancel" | "anchor"; id: string };

export function AnchorWorkspace() {
  const [bank, setBank] = useState<api.AnchorBankState | null>(null);
  const [history, setHistory] = useState<api.AnchorSet[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyId, setHistoryId] = useState("");
  const [coverage, setCoverage] = useState<api.AnchorCoverage | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(true);
  const [page, setPage] = useState<api.AnchorPage | null>(null);
  const [search, setSearch] = useState("");
  const [number, setNumber] = useState("");
  const [type, setType] = useState("");
  const [taskId, setTaskId] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [form, setForm] = useState<{ detail: api.AnchorDetail | null; key: number } | null>(null);
  const pending = useRef(false);
  const detailEpoch = useRef(0);
  const historical = history.find(row => row.id === historyId);
  const selected = historical ?? bank?.working ?? bank?.current;
  const writable = !historical && selected?.status === "DRAFT";
  const selectedId = selected?.id;

  useEffect(() => {
    let current = true;
    api.getAnchorBank().then(data => {
      if (current) { setBank(data); setLoading(false); }
    }).catch(() => { if (current) { setError("Không thể tải bộ anchor. Hãy làm mới để thử lại."); setLoading(false); } });
    return () => { current = false; };
  }, [revision]);

  useEffect(() => {
    if (!bank) return;
    let current = true;
    api.getAnchorCoverage(selectedId).then(data => {
      if (current) { setCoverage(data); setCoverageLoading(false); }
    }).catch(() => { if (current) { setCoverage(null); setCoverageLoading(false); setError("Không thể tải mức độ sẵn sàng. Hãy làm mới để thử lại."); } });
    return () => { current = false; };
  }, [bank, selectedId, revision]);

  useEffect(() => {
    if (!selectedId) return;
    let current = true;
    api.listAnchors({ set_id: selectedId, search, task_number: number ? Number(number) : undefined, task_type: type, writing_task_id: taskId, offset }).then(data => { if (current) setPage(data); }).catch(() => { if (current) setError("Không thể tải bài tham chiếu. Hãy làm mới để thử lại."); });
    return () => { current = false; };
  }, [selectedId, search, number, type, taskId, offset, revision]);

  useEffect(() => {
    if (!historyOpen) return;
    let current = true;
    api.getAnchorHistory().then(data => { if (current) setHistory(data.items); }).catch(() => { if (current) setError("Không thể tải lịch sử thay đổi. Hãy làm mới để thử lại."); });
    return () => { current = false; };
  }, [historyOpen, revision]);

  function close() { detailEpoch.current++; setForm(null); }
  function reload() {
    setCoverage(null); setCoverageLoading(true); setPage(null); setLoading(true);
    setRevision(value => value + 1);
  }
  function returnToCurrent() {
    close(); setHistoryId(""); setOffset(0); setTaskId(""); setPage(null);
    setCoverage(null); setCoverageLoading(true);
  }
  async function mutate(work: () => Promise<void>, closeForm = true) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      await work();
      if (closeForm) close();
      setConfirmation(null); reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Không thể lưu thay đổi. Hãy làm mới rồi thử lại."); }
    finally { pending.current = false; setBusy(false); }
  }
  async function edit(add = false) {
    await mutate(async () => {
      const working = await api.editAnchorBank();
      returnToCurrent();
      setBank(previous => ({ current: previous?.current ?? null, working, current_count: previous?.current_count ?? 0, working_count: previous?.working ? previous.working_count : previous?.current_count ?? 0 }));
      if (add) setForm({ detail: null, key: ++detailEpoch.current });
    }, false);
  }
  function addAnchor() { close(); setForm({ detail: null, key: ++detailEpoch.current }); }
  async function view(id: string) {
    const epoch = ++detailEpoch.current; setError("");
    try { const detail = await api.getAnchor(id); if (epoch === detailEpoch.current) setForm({ detail, key: epoch }); }
    catch { if (epoch === detailEpoch.current) setError("Không thể mở bài tham chiếu. Hãy thử lại."); }
  }
  async function confirm() {
    if (!confirmation) return;
    const target = confirmation;
    await mutate(async () => {
      if (target.kind === "bank") {
        await api.deleteAnchorBank(target.id);
        returnToCurrent(); setBank({ current: null, working: null, current_count: 0, working_count: 0 });
      } else if (target.kind === "cancel") {
        await api.cancelAnchorBank(target.id);
        returnToCurrent(); setBank(previous => previous ? { ...previous, working: null, working_count: 0 } : null);
      } else await api.deleteAnchor(target.id);
    });
  }
  const dialogTitle = confirmation?.kind === "bank" ? "Xóa bộ anchor đang dùng?" : confirmation?.kind === "cancel" ? "Hủy các thay đổi chưa áp dụng?" : "Xóa bài tham chiếu?";
  const dialogDescription = confirmation?.kind === "bank"
    ? "CC, LR và GRA của các lượt chấm mới sẽ không còn dùng TACS và sẽ tự chuyển sang Direct scoring. Các lượt chấm trước đây và dữ liệu lịch sử không bị xóa. Các thay đổi chưa áp dụng cũng sẽ được hủy."
    : confirmation?.kind === "cancel" ? "Các thay đổi đang chỉnh sửa sẽ bị bỏ. Bộ anchor đang dùng và các lượt chấm trước đây được giữ nguyên."
    : "Bài này sẽ được xóa khỏi bộ đang chỉnh sửa. Dữ liệu trong các phiên bản đã dùng để chấm được giữ nguyên.";

  return <div className={styles.workspace} lang="vi">
    {error && !confirmation && <p className="notice notice-error" role="alert">{error}</p>}
    <section className={"surface-card " + styles.panel} aria-label="Bộ anchor hiện tại">
      <div className={styles.heading}>
        <div><h2>{bank?.working ? "Chỉnh sửa bộ anchor" : "Bộ anchor hiện tại"}</h2>
          {bank?.working ? <p className={styles.versionTitle}>{bank.working_count} bài tham chiếu <span className={styles.badge}>Đang chỉnh sửa</span></p>
            : bank?.current ? <p className={styles.versionTitle}>{bank.current_count} bài tham chiếu <span className={styles.readyBadge + " " + styles.badge}>Đang được AI sử dụng</span></p> : null}
        </div>
        <button className="btn btn-ghost" disabled={busy} onClick={() => { setError(""); close(); reload(); }}>Làm mới</button>
      </div>
      {loading ? <p role="status">Đang tải bộ anchor…</p> : !bank ? <p>Chưa xác định được bộ anchor hiện tại.</p> : !bank.current && !bank.working ? <div className={styles.emptyState}><p>Chưa có bộ anchor đang dùng.</p><p>CC, LR và GRA hiện sử dụng Direct scoring.</p></div> : null}
      {bank?.working && <p className={styles.help}>{bank.current ? "Bộ đang dùng vẫn phục vụ chấm AI trong khi bạn chỉnh sửa." : "Bộ này chưa được AI sử dụng."} Bấm Lưu &amp; áp dụng để dùng dữ liệu mới cho các lượt chấm sau.</p>}
      <div className={styles.actions}>
        {bank?.working ? <>
          <button className="btn btn-secondary" disabled={busy || loading} onClick={() => { returnToCurrent(); addAnchor(); }}>Thêm bài tham chiếu</button>
          <button className="btn btn-primary" disabled={busy || loading || Boolean(form)} onClick={() => mutate(async () => {
            const applied = await api.applyAnchorBank(bank.working!.id);
            returnToCurrent(); setBank({ current: applied, working: null, current_count: bank.working_count, working_count: 0 });
          })}>Lưu &amp; áp dụng</button>
          <button className="btn btn-ghost" disabled={busy || loading} onClick={() => { setError(""); setConfirmation({ kind: "cancel", id: bank.working!.id }); }}>Hủy thay đổi</button>
        </> : bank?.current ? <>
          <button className="btn btn-secondary" disabled={busy || loading} onClick={() => edit()}>Sửa</button>
          <button className="btn btn-primary" disabled={busy || loading} onClick={() => edit(true)}>Thêm bài</button>
        </> : <button className="btn btn-primary" disabled={busy || loading || !bank} onClick={() => edit()}>Tạo bộ anchor</button>}
        {bank?.current && <button className="btn btn-danger-ghost" disabled={busy || loading} onClick={() => { setError(""); setConfirmation({ kind: "bank", id: bank.current!.id }); }}>Xóa bộ anchor</button>}
      </div>
      {bank?.working && form && <p className={styles.help}>Lưu hoặc đóng biểu mẫu bài tham chiếu trước khi áp dụng bộ anchor.</p>}
    </section>

    {historical && <div className={styles.historyNotice}><p>Đang xem lịch sử v{historical.version} · Chỉ đọc</p><button className="btn btn-secondary" disabled={busy} onClick={returnToCurrent}>Quay lại bộ hiện tại</button></div>}
    {form && selected && <section className={"surface-card " + styles.panel}><AnchorForm key={selected.id + ":" + form.key + ":" + selected.status} detail={form.detail} readOnly={!writable} busy={busy} onCancel={close} onSave={input => mutate(async () => { if (form.detail) await api.updateAnchor(form.detail.id, input); else await api.createAnchor(selected.id, input); })} /></section>}

    {selected && <section className={"surface-card " + styles.panel} aria-label="Các bài tham chiếu">
      <h2>Các bài tham chiếu{historical ? " · Lịch sử v" + historical.version : ""}</h2>
      <div className={styles.filters}>
        <label>Tìm bài tham chiếu<input maxLength={160} value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} /></label>
        <label>Kỹ năng<select value={number} onChange={e => { setNumber(e.target.value); setOffset(0); }}><option value="">Cả Task 1 và Task 2</option><option value="1">Task 1</option><option value="2">Task 2</option></select></label>
        <label>Dạng bài<input maxLength={64} value={type} onChange={e => { setType(e.target.value); setOffset(0); }} /></label>
        <label>Đề có sẵn<select value={taskId} onChange={e => { setTaskId(e.target.value); setOffset(0); }}><option value="">Tất cả đề</option>{Array.from(new Map(page?.items.filter(a => a.task.id).map(a => [a.task.id!, a.task])).values()).map(task => <option key={task.id!} value={task.id!}>{anchorTaskLabel(task)}</option>)}</select></label>
      </div>
      <div className={styles.overflow}><table><thead><tr><th>Đề Writing</th><th>Số từ</th><th>TA / TR</th><th>CC</th><th>LR</th><th>GRA</th><th>Ngày thêm</th><th>Thao tác</th></tr></thead><tbody>{page?.items.map(anchor => <tr key={anchor.id}>
        <td>{anchorTaskLabel(anchor.task)}<small>{anchor.source_kind === "CUSTOM_TASK" ? "Đề ngoài" : "Đề có sẵn"} · {anchor.task.task_type}<br />{anchor.task.prompt_preview}</small></td>
        <td>{anchor.word_count}</td>{(["ta","cc","lr","gra"] as const).map(trait => <td key={trait}>{anchor.human_scores[trait].toFixed(1)}</td>)}
        <td><time dateTime={anchor.created_at}>{anchor.created_at.slice(0, 10)}</time></td>
        <td><div className={styles.rowActions}><button className="btn btn-secondary" disabled={busy || loading} onClick={() => view(anchor.id)}>{writable ? "Sửa bài" : "Xem"}</button>{writable && <button className="btn btn-ghost" disabled={busy || loading} onClick={() => { setError(""); setConfirmation({ kind: "anchor", id: anchor.id }); }}>Xóa bài tham chiếu</button>}</div></td>
      </tr>)}</tbody></table></div>
      {page?.total === 0 && <div className={styles.emptyState}><p>Chưa có bài tham chiếu phù hợp với bộ lọc hiện tại.</p>{writable && !search && !number && !type && !taskId && <p className={styles.help}>Thêm bài đã chấm thủ công từ đề có sẵn hoặc đề ngoài để bắt đầu.</p>}</div>}
      <nav className={styles.pagination} aria-label="Phân trang bài tham chiếu"><button className="btn btn-secondary" disabled={busy || !offset} onClick={() => setOffset(value => Math.max(0, value - 25))}>Trước</button><span>{page?.total ?? 0} bài</span><button className="btn btn-secondary" disabled={busy || !page || offset + page.limit >= page.total} onClick={() => setOffset(value => value + 25)}>Sau</button></nav>
    </section>}

    <AnchorCoveragePanel coverage={coverage} loading={coverageLoading} editing={writable} historicalVersion={historical?.version} />
    <details className={styles.disclosure} aria-label="Lịch sử thay đổi" onToggle={event => setHistoryOpen(event.currentTarget.open)}>
      <summary>Lịch sử thay đổi</summary>
      <div className={styles.disclosureBody}>
        <p className={styles.help}>Các phiên bản đã dùng được giữ chỉ đọc để đối chiếu các lượt chấm trước đây.</p>
        {!history.length ? <p>Chưa có phiên bản đã lưu.</p> : <ul className={styles.historyList}>{history.map(row => <li key={row.id}><div><strong>v{row.version}</strong><span>{row.status === "ACTIVE" ? "Hiện tại" : "Đã thay thế / ngừng dùng"}{row.retired_at ? " · " + new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date(row.retired_at)) : ""}</span></div><button className="btn btn-secondary" disabled={busy || loading} onClick={() => { close(); setHistoryId(row.id); setOffset(0); setTaskId(""); setPage(null); setCoverage(null); setCoverageLoading(true); }}>Xem</button></li>)}</ul>}
      </div>
    </details>
    <ConfirmDialog open={Boolean(confirmation)} title={dialogTitle} description={dialogDescription} confirmLabel={confirmation?.kind === "bank" ? "Xóa bộ anchor" : confirmation?.kind === "cancel" ? "Hủy thay đổi" : "Xóa bài tham chiếu"} cancelLabel="Hủy" pendingLabel="Đang xử lý…" pending={busy} errorMessage={error || undefined} onCancel={() => { if (!busy) { setConfirmation(null); setError(""); } }} onConfirm={() => void confirm()} />
  </div>;
}
