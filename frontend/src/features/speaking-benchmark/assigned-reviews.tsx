"use client";

import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { LabNavigation } from "./lab-navigation";
import styles from "./quality/quality.module.css";
import { useEffect, useState } from "react";
import { reviewerAssignments, type RaterAssignment } from "@/lib/api/speaking-benchmark-human";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function AssignedReviews() {
  const { t } = useTranslation();
  const [items, setItems] = useState<RaterAssignment[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    reviewerAssignments(offset).then(page => { if (active) { setItems(page.items); setTotal(page.total); setError(""); } }).catch(e => { if (active) setError(String(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [offset, retry]);
  return <div className={styles.stack}>
    <PageHeading eyebrow={t("speakingLab.title")} title={t("speakingUx.myAssignments")} description={t("speakingReviewer.instructions")} />
    <LabNavigation current="reviewer" />
    <section className={styles.panel} aria-busy={loading}>
      {error && <p role="alert" className="notice notice-error">{error}<button className="btn btn-secondary" onClick={() => { setLoading(true); setRetry(value => value + 1); }}>{t("common.retry")}</button></p>}
      {loading ? <p role="status">{t("speakingUx.loadingAssignments")}</p> : !items.length ? <p>{t("speakingUx.assignmentEmpty")}</p> : <ul>{items.map(row => <li key={row.id}><Link href={`/admin/speaking-benchmark/reviewer/${encodeURIComponent(row.id)}`}>{t("speakingUx.assignment", { id: row.id.substring(0, 8) })} · {t("speakingLab.revision", { revision: row.review_revision })}</Link></li>)}</ul>}
      <div className={styles.actions}>
        <button className="btn btn-secondary" disabled={loading || offset === 0} onClick={() => { setLoading(true); setOffset(Math.max(0, offset - 25)); }}>{t("common.previous")}</button>
        <button className="btn btn-secondary" disabled={loading || offset + 25 >= total} onClick={() => { setLoading(true); setOffset(offset + 25); }}>{t("common.next")}</button>
      </div>
    </section>
  </div>;
}
