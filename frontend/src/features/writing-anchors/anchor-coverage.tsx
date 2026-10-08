import type { AnchorCoverage } from "@/lib/api/writing-anchors";
import { anchorTaskLabel, criterionNames, readinessLabels, recommendationLabel } from "./anchor-presentation";
import styles from "./anchor-workspace.module.css";

const languageCriteria = ["cc", "lr", "gra"] as const;
const wholeBands = [5, 6, 7, 8, 9];
const researchBands = [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9];
const allBands = Array.from({ length: 19 }, (_, index) => index / 2);
const otherResearchBands = allBands.filter(band => band < 5);
type CountRow = { id: string; label: string; counts: Record<string, number> };

function BandCountTable({ caption, rows, bands }: { caption: string; rows: CountRow[]; bands: number[] }) {
  return <div className={styles.overflow} role="region" aria-label={caption} tabIndex={0}>
    <table className={styles.countTable}>
      <caption>{caption}</caption>
      <thead><tr><th scope="col">Tiêu chí / đề Writing</th>{bands.map(band => <th scope="col" key={band}>Band {band}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}><th scope="row">{row.label}</th>{bands.map(band => <td key={band}>{row.counts[String(band)] ?? 0}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

export function AnchorCoveragePanel({ coverage, loading = false, onAddAnchor, busy = false, editing = false, historicalVersion }: {
  coverage: AnchorCoverage | null;
  loading?: boolean;
  onAddAnchor?: () => void;
  busy?: boolean;
  editing?: boolean;
  historicalVersion?: number;
}) {
  const hasTask1Data = coverage?.production_task1.some(row => Object.values(row.counts).some(count => count > 0));
  const productionRows = coverage?.production_task1.map(row => ({ id: row.criterion, label: row.criterion.toUpperCase(), counts: row.counts })) ?? [];
  const taRows = coverage?.research_task1_ta.map((row, index) => ({ id: row.source_id ?? row.task.id ?? String(index), label: `${anchorTaskLabel(row.task)} · TA`, counts: row.counts })) ?? [];
  const task2Rows = coverage?.research_task2.map(row => ({ id: row.criterion, label: row.criterion === "ta" ? "TR" : row.criterion.toUpperCase(), counts: row.counts })) ?? [];

  return <section className={styles.coverage} aria-label="Mức độ sẵn sàng của anchor — Task 1">
    <div><h2>Mức độ sẵn sàng của anchor — Task 1</h2><p className={styles.help}>{historicalVersion !== undefined ? `Dữ liệu lịch sử v${historicalVersion}, chỉ để đối chiếu; không thay đổi bộ đang dùng.` : editing ? "Xem trước dữ liệu đang chỉnh sửa. Chỉ dùng cho các lượt chấm mới sau khi Lưu & áp dụng." : "Dữ liệu của bộ anchor đang dùng."}</p></div>
    <div className={styles.callout}>
      <p><strong>Task Achievement (TA)</strong> luôn được chấm trực tiếp bằng Direct dựa trên biểu đồ/hình ảnh. TA không dùng anchor.</p>
      <p><strong>CC / LR / GRA</strong> dùng TACS (so sánh với bài tham chiếu) khi đủ anchor; nếu chưa đủ, hệ thống tự dùng Direct (chấm trực tiếp).</p>
    </div>
    <p className={styles.task2Summary}><strong>Task 2 · TR / CC / LR / GRA:</strong> hiện vẫn dùng MTS. Anchor Task 2 chỉ phục vụ đánh giá/nghiên cứu.</p>

    {!coverage ? <p role="status">{loading ? "Đang tải mức độ sẵn sàng…" : "Không thể tải mức độ sẵn sàng. Hãy làm mới để thử lại."}</p> : <>
      {((!editing && historicalVersion === undefined && !coverage.active_set) || !hasTask1Data) && <div className={styles.emptyState}>
        <p><strong>{historicalVersion !== undefined ? "Phiên bản lịch sử này chưa có bài tham chiếu Task 1." : editing ? "Chưa có bài tham chiếu Task 1 trong bộ đang chỉnh sửa." : !coverage.active_set ? "Chưa có bộ anchor đang hoạt động." : "Bộ anchor đang dùng chưa có bài tham chiếu Task 1."}</strong></p>
        <p>{historicalVersion !== undefined ? "Số liệu này chỉ để đối chiếu, không quyết định cách chấm hiện tại." : editing ? "Cần bổ sung dữ liệu CC, LR và GRA để có thể dùng TACS sau khi áp dụng." : "CC, LR và GRA hiện sẽ tự động dùng Direct scoring."}</p>
        {onAddAnchor && <><p className={styles.help}>Thêm bài tham chiếu để bắt đầu xây dựng TACS.</p><button className="btn btn-secondary" disabled={busy} onClick={onAddAnchor}>Thêm bài tham chiếu</button></>}
      </div>}
      <div className={styles.readinessGrid}>{languageCriteria.map(criterion => {
        const row = coverage.production_task1.find(item => item.criterion === criterion);
        const readiness = row?.readiness ?? "EMPTY";
        const usable = readiness === "PAIRWISE_USABLE" || readiness === "RECOMMENDED_COVERAGE";
        return <article className={styles.readinessCard} key={criterion} aria-label={`Mức sẵn sàng ${criterion.toUpperCase()}`}>
          <header><h3>{criterion.toUpperCase()}</h3><small>{criterionNames[criterion]}</small></header>
          <span className={`${styles.badge} ${usable ? styles.readyBadge : ""}`}>{readinessLabels[readiness]}</span>
          <p className={styles.scoringRoute}>{historicalVersion !== undefined ? "Số liệu lịch sử · Chỉ đọc" : editing ? usable ? "Có thể dùng TACS sau khi áp dụng" : "Sẽ dùng Direct nếu áp dụng lúc này" : usable ? "Chấm bằng TACS" : "Tự động dùng Direct"}</p>
          <dl className={styles.bandGrid}>{wholeBands.map(band => <div key={band}><dt>Band {band}</dt><dd>{row?.counts[String(band)] ?? 0}</dd></div>)}</dl>
          <dl className={styles.usableRange}><dt>Dải band có thể dùng</dt><dd>{row?.ladder.join(" → ") || "Chưa có"}</dd></dl>
        </article>;
      })}</div>
      <p className={styles.help}>Dải band liên tiếp là các mức điểm có đủ bài tham chiếu để hệ thống so sánh.</p>
    </>}

    <section className={styles.target} aria-label="Mục tiêu nên bắt đầu">
      <div><h3>Mục tiêu nên bắt đầu</h3><p>Cho từng tiêu chí CC, LR và GRA:</p></div>
      <ul className={styles.targetBands}>{[6, 7, 8].map(band => <li key={band}><strong>Band {band}</strong><span>khoảng 2 bài</span></li>)}</ul>
      <p className={styles.help}>Khi dữ liệu nhiều hơn, có thể mở rộng sang Band 5 và Band 9, khoảng 3 bài cho mỗi band.</p>
    </section>

    <details className={styles.disclosure} aria-label="Chi tiết kỹ thuật">
      <summary>Chi tiết kỹ thuật</summary>
      <div className={styles.disclosureBody}>
        <p>Dải band có thể dùng gồm ít nhất hai band nguyên liền nhau, mỗi band có bài tham chiếu. Điểm nửa band vẫn được lưu nhưng không tạo dải so sánh trong phiên bản hiện tại.</p>
        <p>Nếu thiếu dải band này, CC, LR và GRA tự động dùng Direct. TA luôn dùng Direct dựa trên biểu đồ/hình ảnh; dữ liệu nghiên cứu không quyết định mức sẵn sàng của Task 1.</p>
        {coverage ? <>
          <p>Ngân sách hiện tại: <strong>{coverage.node_budget} node</strong> (mặc định 2). Mỗi node thực hiện hai lượt so sánh với thứ tự đảo ngược để giảm thiên lệch vị trí (position bias).</p>
          <p>Tối đa lý thuyết: <strong>{coverage.node_budget * 2} lượt so sánh cho mỗi tiêu chí ngôn ngữ</strong> và <strong>{coverage.node_budget * 2 * languageCriteria.length} lượt cho một bài Task 1</strong>, chưa tính phân tích hình ảnh, các lượt chấm Direct và tổng hợp nhận xét. Đây là giới hạn số lượt gọi lý thuyết, không phải số đo độ trễ thực tế.</p>
          {productionRows.length > 0 && <BandCountTable caption="Task 1 · Số bài theo từng band (gồm điểm nửa band)" rows={productionRows} bands={allBands} />}
          {coverage.production_task1.length > 0 && <div className={styles.overflow}><table><caption>Trạng thái chi tiết của bộ đang xem</caption><thead><tr><th scope="col">Tiêu chí</th><th scope="col">Mã mức sẵn sàng</th><th scope="col">Mục tiêu Band 6/7/8</th></tr></thead><tbody>{coverage.production_task1.map(row => <tr key={row.criterion}><th scope="row">{row.criterion.toUpperCase()}</th><td>{row.readiness}</td><td>{row.pilot_complete ? "Đã đạt" : "Chưa đạt"}</td></tr>)}</tbody></table></div>}
          {coverage.recommendations.length > 0 && <><h3>Hướng dẫn xây dựng dữ liệu</h3><ul className={styles.technicalNotes}>{coverage.recommendations.map(text => <li key={text}>{recommendationLabel(text)}</li>)}</ul></>}
        </> : <p>Thông số và số bài chi tiết sẽ xuất hiện khi tải được dữ liệu.</p>}
      </div>
    </details>

    <details className={styles.disclosure} aria-label="Dữ liệu nghiên cứu">
      <summary>Dữ liệu nghiên cứu</summary>
      <div className={styles.disclosureBody}>
        <p className={styles.help}>Số bài bên dưới thuộc bộ anchor {historicalVersion !== undefined ? `lịch sử v${historicalVersion}` : editing ? "đang chỉnh sửa" : "đang dùng"}. Điểm TA của đề ngoài không có hình chỉ là dữ liệu nghiên cứu, không phải benchmark TA có thể tái lập dựa trên hình.</p>
        <h3>Task 1 — TA</h3>
        <p>Điểm TA được lưu để đánh giá độ chính xác của AI. Production Task 1 không dùng TA anchor để chấm.</p>
        {taRows.length ? <BandCountTable caption="Task 1 · TA theo đề Writing" rows={taRows} bands={researchBands} /> : <p>Chưa có dữ liệu nghiên cứu TA.</p>}
        <h3>Task 2</h3>
        <p>Task 2 hiện vẫn dùng MTS cho TR, CC, LR và GRA. Các anchor Task 2 được lưu cho benchmark (đánh giá đối chiếu) và khả năng triển khai TACS trong tương lai.</p>
        {task2Rows.length ? <BandCountTable caption="Task 2 · Số bài theo tiêu chí" rows={task2Rows} bands={researchBands} /> : <p>Chưa có dữ liệu nghiên cứu Task 2.</p>}
        {(taRows.length > 0 || task2Rows.length > 0) && <details className={styles.additionalBands}>
          <summary>Các band khác (0–4.5)</summary>
          {taRows.length > 0 && <BandCountTable caption="Task 1 · TA ở Band 0–4.5" rows={taRows} bands={otherResearchBands} />}
          {task2Rows.length > 0 && <BandCountTable caption="Task 2 · Số bài ở Band 0–4.5" rows={task2Rows} bands={otherResearchBands} />}
        </details>}
      </div>
    </details>
  </section>;
}
