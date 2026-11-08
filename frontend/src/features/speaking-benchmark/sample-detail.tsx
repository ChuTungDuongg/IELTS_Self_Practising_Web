"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import * as api from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "./errors";
import { AudioReviewPlayer, useSourcePlayback } from "./audio-review-player";
import { SpeakerTimeline } from "./speaker-timeline";
import { SegmentEditor } from "./segment-editor";
import { PartBoundaryEditor } from "./part-boundary-editor";
import { GroundTruthForm } from "./ground-truth-form";
import { DiarizationJobStatus } from "./job-status";
import { ApprovalControls } from "./approval-controls";
import { SampleMetadataEditor } from "./metadata-editor";
import { SpeakingEvaluation } from "./evaluation/speaking-evaluation";
import { RecordingWorkspace } from "./recording-workspace";
import { ReferenceEditor } from "./research/reference-editor";
import styles from "./lab.module.css";

export function SpeakingBenchmarkDetail({ sampleId }: { sampleId: string }) {
  const { t } = useTranslation(); const router = useRouter(); const playback = useSourcePlayback();
  const stopPlayback = playback.stop;
  const [sample, setSample] = useState<api.SpeakingSample | null>(null); const [review, setReview] = useState<api.SpeakingReview | null>(null); const [draft, setDraft] = useState<api.SpeakingDraft | null>(null); const [labels, setLabels] = useState<api.SpeakingLabels | null>(null); const [available, setAvailable] = useState<api.SpeakingAvailability | null>(null);
  const [dirty, setDirty] = useState(false); const [labelDirty, setLabelDirty] = useState(false); const dirtyRef = useRef(false);
  const translateRef = useRef(t); useEffect(() => { translateRef.current = t; }, [t]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [generation, setGeneration] = useState(0); const [dialog, setDialog] = useState<"approve" | "delete" | "suggest" | "reload" | "leave" | null>(null);
  const [referenceDirty, setReferenceDirty] = useState(false);
  const [metadataDirty, setMetadataDirty] = useState(false); const [reloadGeneration, setReloadGeneration] = useState(0);
  const [historyRevision, setHistoryRevision] = useState(1); const [historical, setHistorical] = useState<api.SpeakingReview | null>(null);
  const refresh = useCallback(async (discard = false) => {
    const [row, human, readiness] = await Promise.all([api.getSpeakingSample(sampleId), api.getSpeakingLabels(sampleId), api.speakingAvailability()]);
    const current = row.review_revision ? await api.getSpeakingReview(sampleId) : null;
    if (dirtyRef.current && !discard) return;
    setError("");
    setSample(row); setLabels(human); setAvailable(readiness); setReview(current); setDraft(current?.draft ?? null); setDirty(false); setLabelDirty(false); setMetadataDirty(false); setHistorical(null); if (discard) setReloadGeneration(v => v + 1);
  }, [sampleId]);
  useEffect(() => { let active = true; void Promise.resolve().then(() => refresh()).catch(failure => { if (active) setError(labError(failure, translateRef.current)); }); return () => { active = false; stopPlayback(); }; }, [refresh, stopPlayback]);
  useEffect(() => { dirtyRef.current = dirty || labelDirty || metadataDirty || referenceDirty; function warn(event: BeforeUnloadEvent) { if (dirtyRef.current) event.preventDefault(); } window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty, labelDirty, metadataDirty, referenceDirty]);
  function edit(value: api.SpeakingDraft) { dirtyRef.current = true; setDraft(value); setDirty(true); }
  async function operation(action: () => Promise<void>) { setBusy(true); setError(""); try { await action(); setDialog(null); } catch (failure) { setError(labError(failure, t)); } finally { setBusy(false); } }
  async function acknowledge(value: api.SpeakingReview) { setReview(value); setDraft(value.draft); setDirty(false); setSample(await api.getSpeakingSample(sampleId)); }
  function finished() { if (dirtyRef.current) return; void refresh().catch(failure => setError(labError(failure, t))); }
  async function confirm() {
    await operation(async () => {
      if (dialog === "approve" && review) await acknowledge(await api.approveSpeakingReview(sampleId, review.revision));
      if (dialog === "suggest" && review && draft) edit(await api.suggestSpeakingWindows(sampleId, draft, review.revision));
      if (dialog === "reload") await refresh(true);
      if (dialog === "delete" && sample) { await api.deleteSpeakingSample(sampleId, sample.revision); router.push("/admin/speaking-benchmark"); }
      if (dialog === "leave") router.push("/admin/speaking-benchmark");
    });
  }
  if (!sample || !available || !labels) return <div><p role={error ? "alert" : "status"} className="notice">{error || t("common.loading")}</p>{error && <button className="btn btn-secondary" onClick={() => void operation(refresh)}>{t("common.retry")}</button>}</div>;
  return <>
    <PageHeading eyebrow={t("speakingLab.title")} title={sample.code} description={`${sample.status} · ${Math.round(sample.duration_ms / 1000)} s · ${sample.split}`} action={<button className="btn btn-secondary" onClick={() => dirtyRef.current ? setDialog("leave") : router.push("/admin/speaking-benchmark")}>{t("speakingLab.back")}</button>} />
    <div className={`${styles.actions} ${styles.recordingToolbar}`}><button className="btn btn-secondary" disabled={busy || !available.can_queue || dirty || labelDirty || metadataDirty || referenceDirty} onClick={() => void operation(async () => { await api.queueSpeakingDiarization(sampleId); setSample(await api.getSpeakingSample(sampleId)); setGeneration(v => v + 1); })}>{t("speakingLab.diarize")}</button><button className="btn btn-ghost" disabled={busy} onClick={() => setDialog("reload")}>{t("speakingLab.reload")}</button><button className="btn btn-ghost" disabled={busy} onClick={() => setDialog("delete")}>{t("speakingLab.delete")}</button></div>
    {!available.can_queue && <p className="notice" role="status">{t("speakingLab.workerUnavailable")} ({available.reason})</p>}
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    <AudioReviewPlayer sampleId={sampleId} durationMs={sample.duration_ms} playback={playback} />
    <RecordingWorkspace references={<ReferenceEditor sampleId={sampleId} reviewRevision={review?.revision ?? 0} onPlay={(start, end) => playback.play([{ start_ms: start, end_ms: end }])} onDirty={value => { dirtyRef.current = dirty || labelDirty || metadataDirty || value; setReferenceDirty(value); }} />} review={<div className={styles.reviewLayout}>
      <div className={styles.stack}>
        <div className={styles.sectionIntro}><h2>{t("speakingLab.reviewTab")}</h2><p>{t("speakingLab.reviewHelp")}</p></div>
        {review && draft ? <><SpeakerTimeline review={review} draft={draft} disabled={busy || metadataDirty} onChange={edit} onPlay={playback.play} onSeek={playback.seek} /><PartBoundaryEditor draft={draft} disabled={busy || metadataDirty} durationMs={sample.duration_ms} onChange={edit} /><SegmentEditor draft={draft} disabled={busy || metadataDirty} durationMs={sample.duration_ms} onChange={edit} onPlay={playback.play} onSuggest={() => setDialog("suggest")} />
        </> : <p className="notice">{t("speakingLab.awaitReview")}</p>}
      </div>
      <aside className={styles.stack} aria-label={t("speakingLab.reviewActions")}>{review && draft && <ApprovalControls review={review} dirty={dirty} busy={busy || metadataDirty} onSave={() => void operation(async () => acknowledge(await api.saveSpeakingReview(sampleId, draft, review.revision)))} onApprove={() => setDialog("approve")} />}<DiarizationJobStatus sampleId={sampleId} generation={generation} onFinished={finished} />{review && <details className={styles.panel}><summary>{t("speakingLab.history")}</summary><div className={styles.actions}><label>{t("speakingLab.revision", { revision: "" })}<input className="field" type="number" min={1} max={sample.review_revision} value={historyRevision} onChange={e => setHistoryRevision(Number(e.target.value))} /></label><button className="btn btn-secondary" disabled={busy} onClick={() => void operation(async () => setHistorical(await api.getSpeakingReview(sampleId, historyRevision)))}>{t("speakingLab.openRevision")}</button></div>{historical && <><p>{t(historical.approved_at ? "speakingLab.approved" : "common.saved")} · {historical.draft.segments.length} {t("speakingLab.responses")}</p><button className="btn btn-secondary" disabled={busy || metadataDirty} onClick={() => { edit(historical.draft); setHistorical(null); }}>{t("speakingLab.restoreDraft")}</button></>}</details>}<SampleMetadataEditor key={`${sample.revision}:${reloadGeneration}`} sample={sample} disabled={busy || dirty || labelDirty} onDirty={value => { dirtyRef.current = dirty || labelDirty || value; setMetadataDirty(value); }} onSaved={setSample} /></aside>
    </div>} labels={<div className={styles.labelsWorkspace}><GroundTruthForm key={`${sampleId}:${labels.revision}:${reloadGeneration}`} disabled={busy || metadataDirty} sampleId={sampleId} initial={labels} onDirty={value => { dirtyRef.current = dirty || value || metadataDirty; setLabelDirty(value); }} onSaved={async value => { const current = await api.getSpeakingSample(sampleId); setSample(current); setLabels(value); }} /></div>} evaluation={<SpeakingEvaluation sampleId={sampleId} reviewRevision={review?.revision ?? 0} labelRevision={labels.revision} onPlay={(start_ms, end_ms) => playback.play([{ start_ms, end_ms }])} />} />
    <ConfirmDialog open={dialog !== null} title={t(dialog === "approve" ? "speakingLab.approve" : dialog === "delete" ? "speakingLab.delete" : dialog === "suggest" ? "speakingLab.suggest" : "speakingLab.reload")} description={t(dialog === "approve" ? "speakingLab.approveConfirm" : dialog === "delete" ? "speakingLab.deleteConfirm" : dialog === "suggest" ? "speakingLab.suggestConfirm" : "speakingLab.discardConfirm")} confirmLabel={t("speakingLab.confirm")} pending={busy} errorMessage={error || undefined} onCancel={() => setDialog(null)} onConfirm={() => void confirm()} />
  </>;
}
