"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { createResource, updateResource, uploadResource, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { safeHttpUrl } from "./safe-markdown";
import { useStreamText } from "./stream/messages";
export function ResourceEditor({ classroomId, resource, sections, sectionId, onDone, onCancel, initialKind = "TEXT" }: {
  classroomId: string; resource?: ClassroomResource; sections: ClassroomSection[]; sectionId?: string | null; onDone: () => Promise<unknown>; onCancel: () => void; initialKind?: "TEXT" | "LINK" | "FILE";
}) {
  const { ct } = useContentTranslation(), hintId = useId();
  const { tt } = useStreamText(), [saved, setSaved] = useState(false);
  const [kind, setKind] = useState<"TEXT" | "LINK" | "FILE">(resource?.kind ?? initialKind), [title, setTitle] = useState(resource?.title ?? ""), [description, setDescription] = useState(resource?.description ?? ""), [body, setBody] = useState(resource?.body ?? ""), [url, setUrl] = useState(resource?.url ?? ""), [target, setTarget] = useState(sectionId ?? "");
  const [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null); const running = useRef(false), fileInput = useRef<HTMLInputElement>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (running.current || saved) return;
    if (!title.trim() || kind === "TEXT" && !body.trim()) { setError(ct("required")); return; }
    if (kind === "LINK" && !safeHttpUrl(url.trim())) { setError(ct("urlInvalid")); return; }
    const file = fileInput.current?.files?.[0]; if (!resource && kind === "FILE" && !file) { setError(ct("fileRequired")); return; }
    if (file && file.size > 20 * 1024 * 1024) { setError(ct("fileTooLarge")); return; }
    const publish = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "publish";
    const status = publish || resource?.status === "PUBLISHED" ? "PUBLISHED" as const : "DRAFT" as const;
    running.current = true; setPending(true); setError(null);
    try {
      const metadata = { title: title.trim(), description: description.trim() || null, status };
      if (resource) await updateResource(classroomId, resource.id, { ...metadata, ...(kind === "TEXT" ? { body: body.trim() } : kind === "LINK" ? { url: url.trim() } : {}) });
      else if (kind === "FILE" && file) await uploadResource(classroomId, { ...metadata, file, section_id: target || null });
      else if (kind !== "FILE") await createResource(classroomId, { ...metadata, kind, section_id: target || null, ...(kind === "TEXT" ? { body: body.trim() } : { url: url.trim() }) });
      setSaved(true);
      try { await onDone(); } catch { setError(tt("savedRefresh")); }
    } catch (caught) { setError(contentError(caught, ct("error"))); } finally { running.current = false; setPending(false); }
  }
  return <form className="classroom-panel classroom-editor" aria-label={ct(resource ? "editResource" : "addResource")} onSubmit={submit}><h3>{ct(resource ? "editResource" : "addResource")}</h3><fieldset disabled={pending || saved}>
    <label className="field-label">{ct("resourceTitle")}<input className="field" maxLength={240} required value={title} autoFocus onChange={event => setTitle(event.target.value)} /></label>
    <label className="field-label">{ct("description")}<textarea className="field" value={description} rows={2} maxLength={4000} onChange={event => setDescription(event.target.value)} /></label>
    {!resource ? <label className="field-label">{ct("kind")}<select className="select-field" value={kind} onChange={event => setKind(event.target.value as typeof kind)}><option value="TEXT">{ct("text")}</option><option value="LINK">{ct("link")}</option><option value="FILE">{ct("file")}</option></select></label> : null}
    {kind === "TEXT" ? <div><label className="field-label">{ct("lessonBody")}<textarea className="field" rows={8} value={body} maxLength={50000} onChange={event => setBody(event.target.value)} required aria-describedby={hintId} /></label><p id={hintId} className="classroom-meta">{ct("markdownHint")}</p></div> : null}
    {kind === "LINK" ? <label className="field-label">{ct("url")}<input className="field" type="url" maxLength={2048} required value={url} onChange={event => setUrl(event.target.value)} /></label> : null}
    {kind === "FILE" && !resource ? <div><label className="field-label">{ct("upload")}<input className="field" ref={fileInput} type="file" required accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.docx" aria-describedby={hintId} /></label><p id={hintId} className="classroom-meta">{ct("fileHint")}</p></div> : null}
    {!resource ? <label className="field-label">{ct("section")}<select className="select-field" value={target} onChange={event => setTarget(event.target.value)}><option value="">{ct("uncategorized")}</option>{sections.filter(item => item.status !== "ARCHIVED").map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label> : null}
    <div className="classroom-toolbar"><button className="btn btn-primary" type="submit" value="draft">{ct(pending ? "working" : resource?.status === "PUBLISHED" ? "save" : "saveDraft")}</button>{resource?.status !== "PUBLISHED" ? <button className="btn btn-secondary" type="submit" value="publish">{ct("publish")}</button> : null}<button className="btn btn-secondary" type="button" onClick={onCancel}>{ct("cancel")}</button></div>
  </fieldset>{error ? <p className="notice notice-error" role="alert">{error}</p> : null}{saved ? <button type="button" className="btn btn-secondary" disabled={pending} onClick={async () => { if (running.current) return; running.current = true; setPending(true); try { await onDone(); } catch { setError(tt("savedRefresh")); } finally { running.current = false; setPending(false); } }}>{tt("retryLoading")}</button> : null}</form>;
}
