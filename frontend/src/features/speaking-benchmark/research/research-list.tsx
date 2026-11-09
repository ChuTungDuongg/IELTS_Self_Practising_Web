"use client";

import Link from "next/link";
import { LabNavigation } from "../lab-navigation";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import { listExperiments, type ResearchExperimentSummary } from "@/lib/api/speaking-benchmark-research";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "../errors";
import { ExperimentCreate } from "./experiment-create";
import styles from "./research.module.css";

export function ResearchList() {
  const { t } = useTranslation(); const router = useRouter(); const [items, setItems] = useState<ResearchExperimentSummary[]>([]); const [offset, setOffset] = useState(0); const [creating, setCreating] = useState(false); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { setLoading(true); try { setItems(await listExperiments(offset)); setError(""); } catch (failure) { setError(labError(failure, t)); } finally { setLoading(false); } }, [offset, t]);
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  return <div className={styles.stack}><PageHeading eyebrow={t("speakingLab.title")} title={t("speakingResearch.title")} description={t("speakingResearch.description")} />
    <LabNavigation current="research" />
    {error && <p role="alert" className="notice notice-error">{error}<button className="btn btn-ghost" onClick={() => void load()}>{t("common.retry")}</button></p>}
    <section className={styles.panel}><div className={styles.toolbar}><h2>{t("speakingResearch.experiments")}</h2><button className="btn btn-primary" onClick={() => setCreating(v => !v)} aria-expanded={creating}>{t(creating ? "common.cancel" : "speakingResearch.new")}</button></div>
      {loading ? <p role="status">{t("common.loading")}</p> : !items.length ? <p className={styles.muted}>{t("speakingResearch.empty")}</p> : <ul className={styles.list}>{items.map(row => <li key={row.id}><Link href={`/admin/speaking-benchmark/research/${row.id}`}>{row.name}</Link><p className={styles.caption}>{row.mode} · {row.status} · {row.sample_count} {t("speakingLab.samples")} · {row.providers.join(", ")}</p></li>)}</ul>}
      <div className={styles.toolbar}><button className="btn btn-secondary" disabled={loading || !offset} onClick={() => setOffset(v => Math.max(0, v - 25))}>{t("speakingLab.previous")}</button><button className="btn btn-secondary" disabled={loading || items.length < 25} onClick={() => setOffset(v => v + 25)}>{t("speakingLab.next")}</button></div>
    </section>
    {creating && <ExperimentCreate onCreated={row => router.push(`/admin/speaking-benchmark/research/${row.id}`)} />}
  </div>;
}
