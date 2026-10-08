import type { AnchorCoverage } from "@/lib/api/writing-anchors";
import styles from "./anchor-workspace.module.css";

export function AnchorCoveragePanel({ coverage }: { coverage: AnchorCoverage | null }) {
  return <section className={`surface-card ${styles.panel}`} aria-label="Active anchor coverage">
    <h2>Production Task 1 · CC / LR / GRA</h2>
    <p>TA always uses grounded Direct scoring. Language criteria use Direct fallback when a usable contiguous ladder is unavailable.</p>
    <p>Active bank: {coverage?.active_set ? `v${coverage.active_set.version}` : "None"} · Node budget: {coverage?.node_budget ?? 2}</p>
    <div className={styles.overflow}><table><caption>Whole-band density, bands 5–9</caption><thead><tr><th>Criterion</th>{[5,6,7,8,9].map(b => <th key={b}>{b}</th>)}<th>Readiness</th><th>Contiguous ladder</th></tr></thead><tbody>{coverage?.production_task1.map(row => <tr key={row.criterion}><th>{row.criterion.toUpperCase()}</th>{[5,6,7,8,9].map(b => <td key={b}>{row.counts[String(b)] ?? 0}</td>)}<td>{row.readiness.replaceAll("_", " ")} {row.pilot_complete ? "· Pilot complete" : ""}</td><td>{row.ladder.join(" → ") || "None"}</td></tr>)}</tbody></table></div>
    {!coverage?.production_task1.length && <p>No production anchors yet.</p>}
    <p>Pilot: two anchors at each band 6/7/8. Mature: three at each band 5–9. Recommendations are informational; sparse drafts can be activated.</p>
    <h3>Research · Task 1 TA and Task 2</h3><p>These labels do not determine Task 1 production readiness. Task 2 production remains MTS.</p>
    {coverage?.research_task1_ta.map(row => <p key={row.task.id}>{row.task.test_title} · v{row.task.version_number} · TA: {Object.entries(row.counts).map(([band,count]) => `${band}: ${count}`).join(", ") || "Empty"}</p>)}
    {coverage?.research_task2.map(row => <p key={row.criterion}>Task 2 {row.criterion === "ta" ? "TR" : row.criterion.toUpperCase()}: {Object.entries(row.counts).map(([band,count]) => `${band}: ${count}`).join(", ") || "Empty"}</p>)}
    {coverage?.recommendations.map(text => <p key={text}>{text}</p>)}
  </section>;
}
