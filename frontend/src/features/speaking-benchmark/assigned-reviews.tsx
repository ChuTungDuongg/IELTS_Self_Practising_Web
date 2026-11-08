"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { reviewerAssignments, type RaterAssignment } from "@/lib/api/speaking-benchmark-human";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function AssignedReviews() {
  const { t } = useTranslation();
  const [items, setItems] = useState<RaterAssignment[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    reviewerAssignments(offset).then(page => { if (active) { setItems(page.items); setTotal(page.total); setError(""); } }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [offset]);
  return <section className="stack"><h1>{t("speakingLab.blindReviewer")}</h1>
    {error && <p role="alert">{error}</p>}
    <ul>{items.map(row => <li key={row.id}><Link href={`/admin/speaking-benchmark/reviewer/${encodeURIComponent(row.id)}`}>{row.id} · {t("speakingLab.revision", { revision: row.review_revision })}</Link></li>)}</ul>
    <button className="btn btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset-25))}>{t("common.previous")}</button>
    <button className="btn btn-secondary" disabled={offset+25 >= total} onClick={() => setOffset(offset+25)}>{t("common.next")}</button>
  </section>;
}
