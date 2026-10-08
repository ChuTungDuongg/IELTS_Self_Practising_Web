import type { Task1Analysis } from "@/lib/api/task1-visual";
import { presentAIFeedback } from "./ai-feedback-presentation";
import styles from "./writing-ai-assessment.module.css";

const confidenceNames = { HIGH: "Cao", MEDIUM: "Trung bình", LOW: "Thấp", UNUSABLE: "Chưa đủ dữ liệu" };
const verdictNames = {
  SUPPORTED: "Phù hợp với hình", CONTRADICTED: "Chưa khớp với hình",
  INSUFFICIENT_EVIDENCE: "Chưa đủ dữ liệu xác minh", NOT_APPLICABLE: "Không áp dụng",
};

export function Task1VisualStatus({ analysis }: { analysis: Task1Analysis }) {
  const supported = analysis.claims.filter((item) => item.verdict === "SUPPORTED").length;
  const contradicted = analysis.claims.filter((item) => item.verdict === "CONTRADICTED").length;
  const insufficient = analysis.claims.filter((item) => item.verdict === "INSUFFICIENT_EVIDENCE").length;
  return <section className={styles.visualStatus} aria-label="Đối chiếu hình Task 1">
    <p><strong>Độ tin cậy khi đọc hình: {confidenceNames[analysis.confidence]}</strong></p>
    {analysis.confidence === "LOW" ? <p role="status">AI chưa đọc hình với độ tin cậy cao. Hãy xem phần Task Achievement như một gợi ý tham khảo.</p> : null}
    {analysis.confidence === "UNUSABLE" ? <p role="status">AI chưa đọc được hình đủ rõ để chấm Task Achievement. CC, LR và GRA vẫn được chấm từ bài viết.</p> : null}
    {analysis.visual_family === "chart_table" && analysis.cross_check ? <p className={styles.visualNote} role="status">
      <strong>Đối chiếu dữ liệu hình: </strong>
      {analysis.cross_check.status !== "COMPLETED" ? "Không thể dùng bộ đối chiếu chuyên dụng; tiếp tục với phân tích hình chính."
        : analysis.cross_check.disagreement_count ? "Một số số liệu trong hình chưa được AI đọc thống nhất; nhận xét Task Achievement được đưa ra thận trọng hơn."
        : analysis.cross_check.agreement_count ? `${analysis.cross_check.agreement_count} số liệu đã được xác nhận chéo.${analysis.cross_check.warnings.length ? " Một phần dữ liệu chưa được đối chiếu đầy đủ." : ""}`
        : "Chưa đủ dữ liệu trùng khớp để xác nhận chéo; tiếp tục với phân tích hình chính."}
    </p> : null}
    {analysis.claims.length ? <p className={styles.claimCounts}>{supported} nhận định phù hợp · {contradicted} nhận định chưa khớp · {insufficient} nhận định chưa đủ dữ liệu</p> : null}
  </section>;
}

export function Task1VisualDetails({ analysis }: { analysis: Task1Analysis }) {
  return <details className={styles.evidence}>
    <summary>Đối chiếu với hình ({analysis.claims.length} nhận định)</summary>
    {analysis.reference?.summary ? <p className={styles.feedback}>{presentAIFeedback(analysis.reference.summary)}</p> : null}
    {analysis.warnings.some((warning) => warning === "CLAIM_EXTRACTION_FAILED" || warning === "CLAIM_VERIFICATION_FAILED") ? <p className={styles.visualNote}>Một phần đối chiếu chưa hoàn tất. Nhận xét Task Achievement dựa trên thông tin hình đã đọc được; nhận định chưa xác minh không được xem là sai.</p> : null}
    {analysis.claims.map((item) => <blockquote key={item.claim_id}>
      <strong className={styles.verdict}>{verdictNames[item.verdict]}</strong>
      <q>{item.quote}</q>
      <p>{presentAIFeedback(item.explanation)}</p>
    </blockquote>)}
  </details>;
}
