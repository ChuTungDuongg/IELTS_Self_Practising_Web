"use client";
import type { Comparison } from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "../lab.module.css";

export const criteria = ["fc", "lr", "gra", "pr", "overall"] as const;
export const bandText = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);

export function ComparisonTable({ value }: { value: Comparison }) {
  const { t } = useTranslation();
  return <section aria-label={t("speakingEval.comparison")}><h3>{t("speakingEval.comparison")}</h3><p className={styles.muted}>{value.label_status} · {t("speakingEval.labelRevision")}: {value.label_revision ?? "—"}</p><table className={[styles.table, styles.evaluationTable].join(" ")}><thead><tr><th>{t("speakingEval.criterion")}</th><th>{t("speakingEval.human")}</th><th>{t("speakingEval.ai")}</th><th>{t("speakingEval.difference")}</th></tr></thead><tbody>{criteria.map(key => <tr key={key}><th scope="row">{key.toUpperCase()}</th><td>{bandText(value.human[key])}</td><td>{bandText(value.ai[key])}</td><td>{value.differences[key] == null ? "—" : `${value.differences[key] > 0 ? "+" : ""}${value.differences[key].toFixed(1)}`}</td></tr>)}</tbody></table></section>;
}
