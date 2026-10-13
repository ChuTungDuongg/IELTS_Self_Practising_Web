import type { BenchmarkSummary } from "@/lib/api/writing-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./bank.module.css";

export function BenchmarkDistribution({ summary }: { summary: BenchmarkSummary }) {
  const { t } = useTranslation();
  return <div className={styles.distribution}>
    <p className="notice">{t("benchmark.guidance")}</p>
    <div className={styles.distributionTasks}>{summary.tasks.map(task => <section key={task.task_number} className="surface-card" aria-label={t("benchmark.distributionTask", { number: task.task_number })}>
      <h2 className="section-title">{t("benchmark.distributionTask", { number: task.task_number })}</h2>
      <p>{t("benchmark.counts", { complete: task.complete, draft: task.draft, total: task.total })}</p>
      <div className={styles.actions}>{(["DEV", "HOLDOUT"] as const).map(split => <span key={split}>{t("benchmark.splitGuidance", { split: t(split === "DEV" ? "benchmark.dev" : "benchmark.holdout"), actual: task.split_counts[split], target: task.split_targets[split] })}</span>)}</div>
      <details><summary>{t("benchmark.bandDistribution")}</summary><table className={styles.distributionTable}><thead><tr><th scope="col">{t("benchmark.band")}</th><th scope="col">{t("benchmark.actual")}</th><th scope="col">{t("benchmark.suggested")}</th></tr></thead><tbody>{task.overall_distribution.map(bin => <tr key={bin.band}><th scope="row">{bin.band.toFixed(1)}</th><td>{bin.actual}</td><td>{bin.suggested ?? "—"}</td></tr>)}</tbody></table></details>
    </section>)}</div>
  </div>;
}
