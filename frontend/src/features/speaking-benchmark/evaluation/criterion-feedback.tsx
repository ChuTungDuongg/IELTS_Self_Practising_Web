"use client";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "../lab.module.css";

type Feedback = { feedback: string; strengths: string[]; improvements: string[]; local_comments?: { text: string; audio_span?: { start_ms: number; end_ms: number } | null }[] };

export function CriterionFeedback({ value, onPlay }: { value: Feedback; onPlay: (start: number, end: number) => void }) {
  const { t } = useTranslation();
  return <div><p>{value.feedback}</p><ul>{value.strengths.map((text,i) => <li key={i}>{text}</li>)}</ul><ul>{value.improvements.map((text,i) => <li key={i}>{text}</li>)}</ul>{value.local_comments?.map((comment,i) => <div key={i} className={styles.actions}><p>{comment.text}</p>{comment.audio_span && <button className="btn btn-secondary" onClick={() => onPlay(comment.audio_span!.start_ms, comment.audio_span!.end_ms)}>{t("speakingLab.playWindow")} · {(comment.audio_span.start_ms/1000).toFixed(1)}–{(comment.audio_span.end_ms/1000).toFixed(1)} s</button>}</div>)}</div>;
}
