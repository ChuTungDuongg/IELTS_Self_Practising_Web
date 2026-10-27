"use client";

import { useRef, useState, type FormEvent } from "react";
import { createSection, updateSection, type ClassroomSection } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
export function SectionEditor({ classroomId, section, onDone, onCancel }: { classroomId: string; section?: ClassroomSection; onDone: () => Promise<unknown>; onCancel: () => void }) {
  const { ct } = useContentTranslation(); const [title, setTitle] = useState(section?.title ?? ""), [description, setDescription] = useState(section?.description ?? "");
  const [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null); const running = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (running.current) return; if (!title.trim()) { setError(ct("required")); return; }
    running.current = true; setPending(true); setError(null);
    try { const input = { title: title.trim(), description: description.trim() || null }; if (section) await updateSection(classroomId, section.id, input); else await createSection(classroomId, { ...input, status: "DRAFT" }); await onDone(); }
    catch (caught) { setError(contentError(caught, ct("error"))); } finally { running.current = false; setPending(false); }
  }
  return <form className="classroom-panel classroom-editor" onSubmit={submit}><h3>{ct(section ? "editSection" : "addSection")}</h3><fieldset disabled={pending}>
    <label className="field-label">{ct("sectionTitle")}<input className="field" value={title} maxLength={240} required autoFocus onChange={event => setTitle(event.target.value)} /></label>
    <label className="field-label">{ct("description")}<textarea className="field" value={description} rows={3} maxLength={4000} onChange={event => setDescription(event.target.value)} /></label>
    <div className="classroom-toolbar"><button className="btn btn-primary">{ct(pending ? "working" : section ? "save" : "saveDraft")}</button><button type="button" className="btn btn-secondary" onClick={onCancel}>{ct("cancel")}</button></div>
  </fieldset>{error ? <p className="notice notice-error" role="alert">{error}</p> : null}</form>;
}
