"use client";

import { useEffect, useRef, useState } from "react";
import { BuilderIcon } from "@/components/ui/icons";
import type { TestCover } from "@/lib/api/schema";
import { getTest, removeTestCover, uploadTestCover } from "@/lib/api/tests";
import { API_BASE_URL } from "@/lib/api/client";
import { useTranslation } from "@/lib/i18n/locale-provider";
import "./test-cover.css";

export function CoverThumbnail({ cover, title, className = "" }: { cover?: TestCover | null; title: string; className?: string }) {
  const { t } = useTranslation();
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = cover ? `${API_BASE_URL}${cover.content_url}` : null;
  return <span className={`test-cover-thumbnail ${className}`}>
    {url && failedUrl !== url
      // Authenticated API content uses the browser's existing session cookie.
      // eslint-disable-next-line @next/next/no-img-element
      ? <img src={url} alt={t("cover.alt", { title })} loading="lazy" onError={() => setFailedUrl(url)} />
      : <BuilderIcon aria-hidden="true" />}
  </span>;
}

export function CoverManager({ testId, initialCover, title }: { testId: string; initialCover?: TestCover | null; title: string }) {
  const { t } = useTranslation();
  const [cover, setCover] = useState(initialCover ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [pending, setPending] = useState<"upload" | "remove" | null>(null);
  const busy = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function change(operation: "upload" | "remove") {
    if (busy.current || (operation === "upload" && !file)) return;
    busy.current = true; setPending(operation); setMessage(null);
    try {
      const result = operation === "upload" ? await uploadTestCover(testId, file!) : null;
      if (operation === "remove") await removeTestCover(testId);
      setCover(result);
      setFile(null); setPreview(null);
      if (input.current) input.current.value = "";
      setMessage({ error: false, text: t(operation === "upload" ? "cover.success" : "cover.removed") });
      // Refresh from the same summary endpoint used by both libraries.
      const test = await getTest(testId).catch(() => null);
      if (test) setCover(test.cover_image ?? null);
    } catch (error) {
      setMessage({ error: true, text: error instanceof Error ? error.message : t("cover.failed") });
    } finally { busy.current = false; setPending(null); }
  }

  return <section className="test-cover-manager" aria-label={t("cover.title")}>
    <h2>{t("cover.title")}</h2><p>{t("cover.help")}</p>
    <div className="test-cover-manager-body">
      {file && preview
        // eslint-disable-next-line @next/next/no-img-element
        ? <img className="test-cover-preview" src={preview} alt={t("cover.preview")} />
        : <CoverThumbnail cover={cover} title={title} className="test-cover-preview" />}
      <div className="test-cover-controls">
        <label className="field-label">{t("cover.select")}<input ref={input} type="file" accept="image/png,image/jpeg,image/webp" disabled={pending !== null} onChange={event => { const selected = event.target.files?.[0] ?? null; setFile(selected); setPreview(selected ? URL.createObjectURL(selected) : null); setMessage(null); }} /></label>
        <div className="test-cover-actions"><button type="button" className="btn btn-primary" disabled={!file || pending !== null} onClick={() => void change("upload")}>{t(pending === "upload" ? "cover.saving" : "cover.upload")}</button>{file && <button type="button" className="btn btn-secondary" disabled={pending !== null} onClick={() => { setFile(null); setPreview(null); setMessage(null); if (input.current) input.current.value = ""; }}>{t("common.cancel")}</button>}{cover && <button type="button" className="btn btn-secondary" disabled={pending !== null} onClick={() => void change("remove")}>{t(pending === "remove" ? "cover.removing" : "cover.remove")}</button>}</div>
      </div>
    </div>
    {message && <p role={message.error ? "alert" : "status"} className={`notice ${message.error ? "notice-error" : "notice-success"}`}>{message.text}</p>}
  </section>;
}
