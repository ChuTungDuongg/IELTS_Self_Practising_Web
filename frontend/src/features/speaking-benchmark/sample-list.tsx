"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import { listSpeakingSamples, speakingAvailability, type SpeakingAvailability, type SpeakingSample } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import { SpeakingUploadForm } from "./upload-form";
import styles from "./lab.module.css";

export function SpeakingBenchmarkList() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<SpeakingSample[]>([]); const [available, setAvailable] = useState<SpeakingAvailability | null>(null);
  const [offset, setOffset] = useState(0); const [total, setTotal] = useState(0); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { try { const [page, ready] = await Promise.all([listSpeakingSamples(offset), speakingAvailability()]); setError(""); setRows(page.items); setTotal(page.total); setAvailable(ready); } catch (failure) { setError(labError(failure, t)); } finally { setLoading(false); } }, [offset, t]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  return <>
    <PageHeading
      eyebrow={t("admin.administration")}
      title={t("speakingLab.title")}
      description={t("speakingLab.description")}
      action={
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <Link className="btn btn-secondary" href="/admin/speaking-benchmark/reports">{t("speakingEval.reports")}</Link>
          <Link className="btn btn-secondary" href="/admin/speaking-benchmark/research">{t("speakingResearch.title")}</Link>
          <Link className="btn btn-secondary" href="/admin/speaking-benchmark/quality">{t("speakingLab.quality")}</Link>
          <Link className="btn btn-secondary" href="/admin/speaking-benchmark/suites">{t("speakingLab.suites")}</Link>
          <Link className="btn btn-secondary" href="/admin/speaking-benchmark/gates">{t("speakingLab.gates")}</Link>
          <Link className="btn btn-secondary" href="/admin/speaking-benchmark/reviewer">{t("speakingLab.blindReviewer")}</Link>
          <Link className="btn btn-secondary" href="/admin/writing-benchmark">{t("benchmark.title")}</Link>
        </div>
      }
    />
    {error && <p className="notice notice-error" role="alert">{error}<button className="btn btn-ghost" onClick={() => void load()}>{t("common.retry")}</button></p>}
    <div className={styles.layout}>
      <section className={styles.panel} aria-busy={loading}><h2>{t("speakingLab.samples")} ({total})</h2>
        {loading ? <p role="status">{t("common.loading")}</p> : rows.length ? <table className={styles.table}><thead><tr><th>{t("speakingLab.code")}</th><th>{t("speakingLab.status")}</th><th>{t("speakingLab.split")}</th><th>{t("speakingLab.groundTruth")}</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><Link href={`/admin/speaking-benchmark/${row.id}`}>{row.code}</Link><div className={styles.muted}>{Math.round(row.duration_ms / 1000)} s</div></td><td>{row.status}</td><td>{row.split}</td><td>{t(row.label_status === "HUMAN_VERIFIED" ? "speakingLab.verified" : row.label_status === "UNVERIFIED" ? "speakingLab.unverified" : "speakingLab.unlabelled")}</td></tr>)}</tbody></table> : <p className={styles.muted}>{t("speakingLab.empty")}</p>}
        <div className={styles.actions}><button className="btn btn-secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>{t("speakingLab.previous")}</button><button className="btn btn-secondary" disabled={loading || offset + 25 >= total} onClick={() => setOffset(offset + 25)}>{t("speakingLab.next")}</button></div>
      </section>
      {available && <SpeakingUploadForm available={available} onUploaded={() => { if (offset) setOffset(0); else void load(); }} />}
    </div>
  </>;
}
