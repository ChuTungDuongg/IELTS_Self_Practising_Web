"use client";

import { useState } from "react";
import type { QuestionGroupModel } from "@/features/questions/types";
import { uploadAsset } from "@/lib/api/assets";
import { ApiError } from "@/lib/api/client";

export function QuestionImageAttachment({
  group,
  testVersionId,
  onChange,
}: {
  group: QuestionGroupModel;
  testVersionId: string;
  onChange: (group: QuestionGroupModel) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const noun = group.question_type === "diagram_labelling" ? "diagram" : "question image";

  async function upload(file: File) {
    setUploading(true);
    setMessage(null);
    try {
      const asset = await uploadAsset("question-images", testVersionId, file);
      onChange({ ...group, image_asset_id: asset.id, image_asset: asset });
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The image could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="question-image-attachment">
      <div className="question-image-meta"><p className="page-eyebrow">Question image</p><strong>{group.image_asset?.original_name ?? `No ${noun} uploaded`}</strong>{group.image_asset ? <span>{group.image_asset.mime_type} · {(group.image_asset.file_size / 1024).toFixed(0)} KB</span> : <span>PNG, JPEG or WEBP</span>}</div>
      <div className="flex flex-wrap gap-2">
        <label className="btn btn-secondary">{uploading ? "Uploading…" : group.image_asset ? "Replace image" : `Upload ${noun}`}<input aria-label={`Upload ${noun}`} type="file" className="sr-only" accept="image/png,image/jpeg,image/webp" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.currentTarget.value = ""; }} /></label>
        {group.image_asset ? <button type="button" className="btn btn-danger-ghost" disabled={uploading} onClick={() => onChange({ ...group, image_asset_id: null, image_asset: null })}>Remove image</button> : null}
      </div>
      {message ? <p role="alert" className="notice notice-error question-image-error">{message}</p> : null}
    </div>
  );
}
