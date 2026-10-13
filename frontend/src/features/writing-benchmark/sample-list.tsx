import type { BenchmarkListItem } from "@/lib/api/writing-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./bank.module.css";

export function BenchmarkSampleList({ rows, selectedId, disabled, onSelect, onCreate, full }: {
  rows: BenchmarkListItem[]; selectedId?: string; disabled: boolean; full: boolean;
  onSelect: (id: string) => void; onCreate: () => void;
}) {
  const { t } = useTranslation();
  return <section className={`surface-card ${styles.list}`} aria-label={t("benchmark.samples")}>
    <h2 className="section-title">{t("benchmark.samples")}</h2>
    <button type="button" className="btn btn-primary" disabled={disabled || full} onClick={onCreate}>{t("benchmark.new")}</button>
    {full ? <p className="notice">{t("benchmark.capacity")}</p> : null}
    <div className={styles.rows}>
      {rows.map(row => <button key={row.id} type="button" className={styles.row} aria-current={selectedId === row.id ? "true" : undefined} disabled={disabled} onClick={() => onSelect(row.id)}>
        <strong>{row.code}</strong><span>{t(row.status === "COMPLETE" ? "benchmark.completeStatus" : "benchmark.draft")}</span>
        <span>{t(row.split === "DEV" ? "benchmark.dev" : "benchmark.holdout")}</span><span>{row.human_overall?.toFixed(1) ?? "—"}</span>
      </button>)}
      {!rows.length ? <p className="notice">{t("benchmark.noSamples")}</p> : null}
    </div>
  </section>;
}
