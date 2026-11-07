"use client";
import type { Comparison } from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./reports.module.css";

export function ReportCharts({ rows }: { rows: Comparison[] }) {
  const { t } = useTranslation();
  const paired = rows.filter(r => r.verified && r.human.overall != null && r.ai.overall != null);
  const counts = Array.from({ length: 19 }, (_, i) => ({ band: i / 2, human: rows.filter(r => r.verified && r.human.overall === i / 2).length, ai: paired.filter(r => r.ai.overall === i / 2).length }));
  const maximum = Math.max(1, ...counts.flatMap(c => [c.human, c.ai]));
  const errors = Array.from({ length: 37 }, (_, i) => ({ error: i / 2 - 9, count: paired.filter(r => r.ai.overall! - r.human.overall! === i / 2 - 9).length })).filter(r => r.count);
  const errorMax = Math.max(1, ...errors.map(e => e.count));
  return <div className={styles.charts}>
    <figure><figcaption>{t("speakingReport.scatter")}</figcaption><svg role="img" aria-label={t("speakingReport.scatter")} viewBox="0 0 320 210"><line x1="32" y1="180" x2="300" y2="180" className={styles.axis} /><line x1="32" y1="180" x2="32" y2="12" className={styles.axis} /><line x1="32" y1="180" x2="300" y2="12" className={styles.reference} />{paired.map(r => <circle key={r.sample_id} cx={32+r.human.overall!*268/9} cy={180-r.ai.overall!*168/9} r="4" className={styles.ai}><title>{r.code}: {r.human.overall} / {r.ai.overall}</title></circle>)}<text x="32" y="199">0</text><text x="291" y="199">9</text><text x="10" y="18">9</text></svg><p>{t("speakingEval.human")} → · {t("speakingEval.ai")} ↑ · n={paired.length}</p></figure>
    <figure><figcaption>{t("speakingReport.distribution")}</figcaption><svg role="img" aria-label={t("speakingReport.distribution")} viewBox="0 0 320 210">{counts.map((c, i) => <g key={c.band}><rect x={i*16+9} y={180-c.human*150/maximum} width="5" height={c.human*150/maximum} className={styles.human} /><rect x={i*16+15} y={180-c.ai*150/maximum} width="5" height={c.ai*150/maximum} className={styles.ai} />{i%2===0 && <text x={i*16+10} y="199">{c.band}</text>}<title>{c.band}: Human {c.human}, AI {c.ai}</title></g>)}</svg><p><span className={styles.humanKey}>□ {t("speakingEval.human")}</span> · <span>■ {t("speakingEval.ai")}</span></p></figure>
    <figure><figcaption>{t("speakingReport.signed")}</figcaption><svg role="img" aria-label={t("speakingReport.signed")} viewBox="0 0 320 210">{errors.map((e,i) => <g key={e.error}><rect x={20+i*280/Math.max(1,errors.length)} y={180-e.count*150/errorMax} width={Math.min(30,230/Math.max(1,errors.length))} height={e.count*150/errorMax} className={styles.ai} /><text x={20+i*280/Math.max(1,errors.length)} y="199">{e.error>0?"+":""}{e.error}</text><title>{e.error}: {e.count}</title></g>)}</svg><p>{t("speakingEval.difference")}</p></figure>
    <details className={styles.chartTable}><summary>{t("speakingReport.distribution")} · {t("speakingEval.human")} / {t("speakingEval.ai")}</summary><table><thead><tr><th>Band</th><th>{t("speakingEval.human")}</th><th>{t("speakingEval.ai")}</th></tr></thead><tbody>{counts.map(c => <tr key={c.band}><th>{c.band}</th><td>{c.human}</td><td>{c.ai}</td></tr>)}</tbody></table></details>
    <details className={styles.chartTable}><summary>{t("speakingReport.signed")} ({errors.length})</summary><table><thead><tr><th>{t("speakingEval.difference")}</th><th>Count</th></tr></thead><tbody>{errors.map(e => <tr key={e.error}><th>{e.error > 0 ? "+" : ""}{e.error}</th><td>{e.count}</td></tr>)}</tbody></table></details>
  </div>;
}
