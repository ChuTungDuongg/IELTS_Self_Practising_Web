"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import { listSpeakingSamples, speakingAvailability, type SpeakingAvailability, type SpeakingSample } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import { LabNavigation } from "./lab-navigation";
import { SpeakingUploadForm } from "./upload-form";
import styles from "./lab.module.css";

function RecordingTable({ rows }: { rows: SpeakingSample[] }) {
  const { t } = useTranslation();
  return <div className={styles.tableWrap}>
    <table className={styles.table}>
      <thead><tr>
        <th scope="col">{t("speakingLab.code")}</th>
        <th scope="col">{t("speakingLab.status")}</th>
        <th scope="col">{t("speakingLab.split")}</th>
        <th scope="col">{t("speakingLab.groundTruth")}</th>
      </tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}>
        <td><Link href={`/admin/speaking-benchmark/${row.id}`}>{row.code}</Link><div className={styles.muted}>{Math.round(row.duration_ms / 1000)} s</div></td>
        <td>{row.status}</td>
        <td>{row.split}</td>
        <td>{t(row.label_status === "HUMAN_VERIFIED" ? "speakingLab.verified" : row.label_status === "UNVERIFIED" ? "speakingLab.unverified" : "speakingLab.unlabelled")}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

export function SpeakingBenchmarkList() {
  const { t } = useTranslation();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [rows, setRows] = useState<SpeakingSample[]>([]);
  const [available, setAvailable] = useState<SpeakingAvailability | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [page, ready] = await Promise.all([listSpeakingSamples(offset), speakingAvailability()]);
      setError(""); setRows(page.items); setTotal(page.total); setAvailable(ready);
    } catch (failure) { setError(labError(failure, t)); }
    finally { setLoading(false); }
  }, [offset, t]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  return <>
    <PageHeading
      eyebrow={t("admin.administration")}
      title={t("speakingLab.title")}
      description={t("speakingLab.description")}
      action={<button className={`btn ${uploadOpen ? "btn-secondary" : "btn-primary"}`} aria-expanded={uploadOpen} aria-controls="speaking-upload" onClick={() => setUploadOpen(value => !value)}>{t("speakingLab.upload")}</button>}
    />
    <LabNavigation current="recordings" />
    {error && <p className="notice notice-error" role="alert">{error}<button className="btn btn-ghost" onClick={() => void load()}>{t("common.retry")}</button></p>}
    <div className={uploadOpen ? styles.layout : styles.stack}>
      <section className={styles.panel} aria-busy={loading}>
        <h2>{t("speakingLab.samples")} ({total})</h2>
        {loading ? <p role="status">{t("common.loading")}</p> : rows.length ? <RecordingTable rows={rows} /> : <p className={styles.muted}>{t("speakingLab.empty")}</p>}
        <div className={styles.actions}>
          <button className="btn btn-secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>{t("speakingLab.previous")}</button>
          <button className="btn btn-secondary" disabled={loading || offset + 25 >= total} onClick={() => setOffset(offset + 25)}>{t("speakingLab.next")}</button>
        </div>
      </section>
      {available && <div id="speaking-upload" hidden={!uploadOpen}>
        <SpeakingUploadForm available={available} onUploaded={() => { if (offset) setOffset(0); else void load(); }} />
      </div>}
    </div>
  </>;
}
