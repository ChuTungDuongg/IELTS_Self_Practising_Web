"use client";

import type { ASRReference } from "@/lib/api/speaking-benchmark-research";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./research.module.css";

type Span = ASRReference["uncertainty"][number];

export function UncertaintyFields({ spans, start, end, onChange }: {
  spans: Span[];
  start: number;
  end: number;
  onChange(spans: Span[]): void;
}) {
  const { t } = useTranslation();
  const add = () => onChange([...spans, { start_ms: start, end_ms: end, kind: "uncertain" }]);
  function update(index: number, value: Partial<Span>) {
    onChange(spans.map((span, i) => i === index ? { ...span, ...value } : span));
  }
  return <div className={styles.stack}>
    <label className={styles.check}><input type="checkbox" checked={spans.length > 0} onChange={e => e.target.checked ? add() : onChange([])} />{t("speakingResearch.uncertain")}</label>
    {spans.length > 0 && <>
      <p className={styles.caption}>{t("speakingResearch.uncertainHelp")}</p>
      {spans.map((span, index) => <div className={styles.annotation} key={index}>
        <label>{t("speakingResearch.uncertaintyKind")}<select className="field" value={span.kind} onChange={e => update(index, { kind: e.target.value as Span["kind"] })}>
          <option value="uncertain">{t("speakingResearch.uncertaintySpeech")}</option>
          <option value="unintelligible">{t("speakingResearch.unintelligible")}</option>
          <option value="questionable_reference">{t("speakingResearch.questionableReference")}</option>
        </select></label>
        <label>{t("speakingResearch.sourceStart")}<input className="field" type="number" min={start} max={span.end_ms - 1} step={1} value={span.start_ms} onChange={e => update(index, { start_ms: Number(e.target.value) })} /></label>
        <label>{t("speakingResearch.sourceEnd")}<input className="field" type="number" min={span.start_ms + 1} max={end} step={1} value={span.end_ms} onChange={e => update(index, { end_ms: Number(e.target.value) })} /></label>
        <button className="btn btn-ghost" onClick={() => onChange(spans.filter((_, i) => i !== index))}>{t("common.remove")}</button>
      </div>)}
      <button className="btn btn-secondary" onClick={add}>{t("speakingResearch.addUncertainty")}</button>
    </>}
  </div>;
}
