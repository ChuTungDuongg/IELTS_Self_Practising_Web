"use client";

import { useEffect, useState } from "react";
import { fetchResourceFile, type ClassroomResource } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";

export function FileResourcePreview({ resource }: { resource: ClassroomResource }) {
  const { ct, locale } = useContentTranslation();
  const [url, setUrl] = useState<string | null>(null), [error, setError] = useState<unknown>(null), [pending, setPending] = useState(true), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); let objectUrl: string | null = null;
    void fetchResourceFile(resource.classroom_id, resource.id, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); setPending(false);
    }).catch(caught => { if (!controller.signal.aborted) { setError(caught); setPending(false); } });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [resource.classroom_id, resource.id, attempt]);
  return <div>
    <p className="classroom-meta">{resource.original_filename}{resource.size_bytes !== null ? ` · ${new Intl.NumberFormat(locale).format(Math.ceil(resource.size_bytes / 1024))} KB` : ""}</p>
    {pending ? <p role="status">{ct("loading")}</p> : null}
    {error ? <div><p role="alert" className="notice notice-error">{contentError(error, ct("error"))}</p><button className="btn btn-secondary" type="button" onClick={() => { setUrl(null); setError(null); setPending(true); setAttempt(value => value + 1); }}>{ct("retry")}</button></div> : null}
    {url ? <>
      {resource.media_type?.startsWith("image/") ?
        // Authenticated blobs must bypass the public Next image optimizer.
        // eslint-disable-next-line @next/next/no-img-element
        <img className="classroom-image" src={url} alt={resource.title} /> : null}
      <div className="classroom-toolbar"><a className="btn btn-secondary" href={url} target="_blank" rel="noopener noreferrer">{ct("viewFile")}</a><a className="btn btn-secondary" href={url} download={resource.original_filename ?? resource.title}>{ct("download")}</a></div>
    </> : null}
  </div>;
}
