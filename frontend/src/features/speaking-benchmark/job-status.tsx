"use client";

import { useEffect, useRef, useState } from "react";
import { cancelSpeakingJob, getSpeakingJobs, type SpeakingJob } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import styles from "./lab.module.css";

export function DiarizationJobStatus({ sampleId, generation, onFinished }: { sampleId: string; generation: number; onFinished(): void }) {
  const { t } = useTranslation(); const [jobs, setJobs] = useState<SpeakingJob[]>([]); const [error, setError] = useState(""); const [cancelling, setCancelling] = useState(false);
  const notifiedTerminal = useRef("");
  const callback = useRef(onFinished); useEffect(() => { callback.current = onFinished; }, [onFinished]);
  useEffect(() => { let active = true; let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() { try { const list = await getSpeakingJobs(sampleId); if (!active) return; setJobs(list); setError(""); const running = list[0] && ["PENDING", "RUNNING"].includes(list[0].status); if (running) { timer = setTimeout(() => void poll(), 3000); } else if (list[0]) { const terminal = `${sampleId}:${list[0].id}:${list[0].status}`; if (notifiedTerminal.current !== terminal) { notifiedTerminal.current = terminal; callback.current(); } } }
      catch (failure) { if (active) { setError(labError(failure, t)); timer = setTimeout(() => void poll(), 10000); } } }
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [sampleId, generation, t]);
  const job = jobs[0]; const running = job && ["PENDING", "RUNNING"].includes(job.status);
  return <section className={styles.panel}><h2>{t("speakingLab.job")}</h2>{job ? <><div className={styles.status} role="status"><span>{job.status} · {job.stage}</span><progress aria-label={t("speakingLab.job")} value={job.progress} max={100} /><span>{job.progress}%</span></div><p className={styles.muted}>{t("speakingLab.attempts", { count: job.attempts })}</p>{job.error_code && <p role="alert" className="notice notice-error">{job.error_code}</p>}{running && <button className="btn btn-secondary" disabled={cancelling} onClick={async () => { setCancelling(true); try { const cancelled = await cancelSpeakingJob(sampleId, job.id); setJobs([cancelled, ...jobs.slice(1)]); callback.current(); } catch (failure) { setError(labError(failure, t)); } finally { setCancelling(false); } }}>{t("speakingLab.cancelJob")}</button>}</> : <p className={styles.muted}>{t("speakingLab.noJob")}</p>}{error && <p role="alert" className="notice notice-error">{error}</p>}</section>;
}
