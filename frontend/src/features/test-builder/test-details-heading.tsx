"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { updateTest } from "@/lib/api/tests";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";

export function TestDetailsHeading({ testId, initialTitle, initialDescription, versionNumber }: {
  testId: string;
  initialTitle: string;
  initialDescription: string | null;
  versionNumber: number;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [title, setTitle] = useState(initialTitle);
  const [description, setDescription] = useState(initialDescription);
  const [draftTitle, setDraftTitle] = useState(initialTitle);
  const [draftDescription, setDraftDescription] = useState(initialDescription ?? "");
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: "builder.detailsFailed" }>("");
  const errorText = typeof error === "string" ? error : t(error.message);

  function open() {
    setDraftTitle(title);
    setDraftDescription(description ?? "");
    setError("");
    setEditing(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedTitle = draftTitle.trim();
    const normalizedDescription = draftDescription.trim();
    if (!normalizedTitle || normalizedTitle.length > 240 || normalizedDescription.length > 4000 || pending) return;
    setPending(true);
    setError("");
    try {
      const updated = await updateTest(testId, { title: normalizedTitle, description: normalizedDescription || null });
      setTitle(updated.title);
      setDescription(updated.description);
      setDraftTitle(updated.title);
      setDraftDescription(updated.description ?? "");
      setEditing(false);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : { message: "builder.detailsFailed" });
    } finally {
      setPending(false);
    }
  }

  return <>
    <PageHeading eyebrow={t("builder.brand")} title={title} description={t("builder.versionWorkspace", { number: versionNumber })} action={<div className="flex items-center gap-3"><StatusBadge status="DRAFT" label={t("common.draft")} />{!editing ? <button type="button" onClick={open} className="btn btn-secondary">{t("builder.editDetails")}</button> : null}</div>} />
    {description && !editing ? <p className="mt-2 text-sm text-[var(--muted)]">{description}</p> : null}
    {editing ? <form onSubmit={(event) => void save(event)} className="mt-4 max-w-2xl space-y-3 rounded-xl border border-[var(--border)] p-4">
      <label className="field-label">{t("builder.testName")}<input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} maxLength={240} autoFocus disabled={pending} className="field mt-2" /></label>
      <label className="field-label">{t("common.description")}<textarea value={draftDescription} onChange={(event) => setDraftDescription(event.target.value)} maxLength={4000} disabled={pending} rows={3} className="textarea-field mt-2" /></label>
      {error ? <p role="alert" className="notice notice-error">{errorText}</p> : null}
      <div className="flex gap-2"><button type="submit" disabled={pending || !draftTitle.trim() || draftTitle.trim().length > 240 || draftDescription.trim().length > 4000} className="btn btn-primary">{pending ? t("common.saving") : t("common.save")}</button><button type="button" disabled={pending} onClick={() => { setEditing(false); setError(""); }} className="btn btn-secondary">{t("common.cancel")}</button></div>
    </form> : null}
  </>;
}
