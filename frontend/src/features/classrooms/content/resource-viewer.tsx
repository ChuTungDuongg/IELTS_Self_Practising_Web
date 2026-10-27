"use client";

import { useState } from "react";
import { type ClassroomResource } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { SafeMarkdown, safeHttpUrl } from "./safe-markdown";
import { FileResourcePreview } from "./file-resource-preview";
export function ResourceViewer({ resource }: { resource: ClassroomResource }) {
  const { ct } = useContentTranslation(); const [open, setOpen] = useState(false);
  const website = resource.url ? safeHttpUrl(resource.url) : null;
  return <div className="classroom-resource-reader">
    <button type="button" className="classroom-text-button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{ct(open ? "close" : "view")}</button>
    {open ? <div className="classroom-resource-body">
      {resource.description ? <p>{resource.description}</p> : null}
      {resource.kind === "TEXT" ? <SafeMarkdown text={resource.body ?? ""} /> : null}
      {resource.kind === "LINK" && website ? <a className="btn btn-secondary" href={website} target="_blank" rel="noopener noreferrer">{ct("openLink")}</a> : null}
      {resource.kind === "FILE" ? <FileResourcePreview key={resource.id} resource={resource} /> : null}
    </div> : null}
  </div>;
}
