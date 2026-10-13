import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useBuilderLifecycle } from "@/features/test-builder/builder-lifecycle";
import { exportWritingBenchmarkBundle, getWritingBenchmarkSummary, type BenchmarkSummary } from "@/lib/api/writing-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function BenchmarkExportButton({ disabled = false }: { disabled?: boolean }) {
  const { t } = useTranslation(); const life = useBuilderLifecycle();
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [pending, setPending] = useState(false); const [error, setError] = useState(false);
  async function review() {
    setError(false); setPending(true);
    try {
      const result = await life.runTransition(() => getWritingBenchmarkSummary());
      if (result.ready) setSummary(result.value);
      else setError(true);
    } catch { setError(true); }
    finally { setPending(false); }
  }
  async function download() {
    setError(false); setPending(true);
    try {
      const result = await life.runTransition(() => exportWritingBenchmarkBundle());
      if (!result.ready) { setError(true); return; }
      const url = URL.createObjectURL(result.value.blob);
      try { const link = document.createElement("a"); link.href = url; link.download = result.value.filename; link.click(); }
      finally { URL.revokeObjectURL(url); }
      setSummary(null);
    } catch { setError(true); }
    finally { setPending(false); }
  }
  const description = summary ? summary.tasks.map(task => t("benchmark.exportCounts", { number: task.task_number, complete: task.complete, draft: task.draft, dev: task.split_counts.DEV, holdout: task.split_counts.HOLDOUT })).join(" ") + " " + t("benchmark.draftsExcluded") : "";
  return <>
    <button type="button" className="btn btn-primary" disabled={disabled || pending} onClick={() => void review()}>{t("benchmark.export")}</button>
    {error && !summary ? <p className="notice notice-error" role="alert">{t("benchmark.exportFailed")}</p> : null}
    <ConfirmDialog open={summary !== null} title={t("benchmark.export")} description={description} confirmLabel={t("benchmark.download")} pending={pending} errorMessage={error ? t("benchmark.exportFailed") : undefined} onCancel={() => setSummary(null)} onConfirm={() => void download()} />
  </>;
}
