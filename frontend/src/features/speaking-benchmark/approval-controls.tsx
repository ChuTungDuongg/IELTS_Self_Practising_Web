import type { SpeakingReview } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./lab.module.css";
import { approvalIssue } from "./errors";

export function ApprovalControls({ review, dirty, busy, onSave, onApprove }: { review: SpeakingReview; dirty: boolean; busy: boolean; onSave(): void; onApprove(): void }) {
  const { t } = useTranslation();
  return <section className={`${styles.panel} ${styles.approvalPanel}`}><h2>{t("speakingLab.approval")}</h2><p role="status">{t(dirty ? "speakingLab.unsaved" : review.approved_at ? "speakingLab.approved" : "common.saved")} · {t("speakingLab.revision", { revision: review.revision })}</p>
    <p className={styles.muted}>{t("speakingLab.approvalHelp")}</p>
    {!dirty && review.approval_errors.length > 0 && <ul>{review.approval_errors.map(error => <li key={error} className={styles.muted}>{approvalIssue(error, t)}</li>)}</ul>}
    <div className={styles.actions}><button className="btn btn-primary" disabled={busy || !dirty} onClick={onSave}>{t(busy ? "common.saving" : "speakingLab.saveReview")}</button><button className="btn btn-secondary" disabled={busy || dirty || !!review.approved_at || review.approval_errors.length > 0} onClick={onApprove}>{t("speakingLab.approve")}</button></div>
  </section>;
}
