"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { updateTest } from "@/lib/api/tests";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";

export function RenameTestHeading({ testId, initialTitle, versionNumber }: { testId: string; initialTitle: string; versionNumber: number }) {
  const router = useRouter();
  const [title, setTitle] = useState(initialTitle);
  const [draftTitle, setDraftTitle] = useState(initialTitle);
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = draftTitle.trim();
    if (!normalized || normalized.length > 240 || pending) return;
    setPending(true);
    setError("");
    try {
      const updated = await updateTest(testId, { title: normalized });
      setTitle(updated.title);
      setDraftTitle(updated.title);
      setEditing(false);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not rename the test. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return <PageHeading eyebrow="IELTS Studio · Exam Builder" title={title} description={`Version ${versionNumber} · Structured authoring workspace`} action={<div className="flex flex-wrap items-center gap-3"><StatusBadge status="DRAFT" />
    {editing ? <form onSubmit={(event) => void save(event)} className="flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor="rename-test-title">Test title</label>
      <input id="rename-test-title" value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} maxLength={240} autoFocus disabled={pending} className="field" />
      <button type="submit" disabled={pending || !draftTitle.trim() || draftTitle.trim().length > 240} className="btn btn-primary">{pending ? "Saving…" : "Save"}</button>
      <button type="button" disabled={pending} onClick={() => { setDraftTitle(title); setError(""); setEditing(false); }} className="btn btn-secondary">Cancel</button>
      {error ? <p role="alert" className="notice notice-error w-full">{error}</p> : null}
    </form> : <button type="button" onClick={() => { setDraftTitle(title); setError(""); setEditing(true); }} className="btn btn-secondary">Rename test</button>}
  </div>} />;
}
