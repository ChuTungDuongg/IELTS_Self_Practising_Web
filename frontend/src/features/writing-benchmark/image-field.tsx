import { useRef, useState } from "react";
import Image from "next/image";
import type { BenchmarkSample } from "@/lib/api/writing-benchmark";
import { writingBenchmarkImageUrl } from "@/lib/api/writing-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./bank.module.css";

export function BenchmarkImageField({ sample, disabled, onUpload, onRemove }: {
  sample: BenchmarkSample; disabled: boolean; onUpload: (file: File) => Promise<boolean>; onRemove: () => void;
}) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  return <section className={styles.image}>
    {sample.has_image ? <Image unoptimized src={writingBenchmarkImageUrl(sample.id, sample.revision)} alt={t("benchmark.imagePreview")} width={640} height={400} className={styles.preview} /> : null}
    <label className={styles.field}>{t("benchmark.image")}<input ref={input} type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
    <p className="muted">{t("benchmark.imageHint")}</p>
    <div className={styles.actions}>
      <button type="button" className="btn btn-secondary" disabled={disabled || !file} onClick={() => { if (file) void onUpload(file).then(saved => { if (saved) { setFile(null); if (input.current) input.current.value = ""; } }); }}>{t(sample.has_image ? "benchmark.replaceImage" : "benchmark.uploadImage")}</button>
      {sample.has_image ? <button type="button" className="btn btn-ghost" disabled={disabled} onClick={onRemove}>{t("benchmark.removeImage")}</button> : null}
    </div>
  </section>;
}
