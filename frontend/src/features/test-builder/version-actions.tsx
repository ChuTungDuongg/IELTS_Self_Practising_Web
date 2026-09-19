"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api/client";
import { cloneVersion, deleteDraft, publishVersion, validateVersion } from "@/lib/api/tests";
import { useBuilderLifecycle } from "./builder-lifecycle";
import { CheckIcon } from "@/components/ui/icons";

export function VersionActions({ testId, versionId, status }: { testId: string; versionId: string; status: "DRAFT" | "PUBLISHED" | "ARCHIVED" }) {
  const router = useRouter();
  const { beginDelete, deleting } = useBuilderLifecycle();
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const published = status === "PUBLISHED";

  async function act(action: "validate" | "publish" | "clone") {
    setPending(true);
    setMessage(null);
    try {
      if (action === "validate") {
        const result = await validateVersion(versionId);
        setMessage(result.valid ? "Version is valid." : result.errors.map((item) => `${item.path}: ${item.message}`).join(" "));
      } else if (action === "publish") {
        await publishVersion(versionId);
        setMessage("Version published and frozen.");
        router.refresh();
      } else {
        const clone = await cloneVersion(testId, versionId);
        router.push(`/admin/tests/${testId}/versions/${clone.id}/edit`);
        router.refresh();
      }
    } catch (caught) {
      setMessage(caught instanceof ApiError ? caught.message : "The action failed.");
    } finally {
      setPending(false);
    }
  }

  async function removeDraft() {
    if (pending || deleting) return;
    setPending(true);
    setMessage(null);
    try {
      await beginDelete(() => deleteDraft(testId, versionId));
      router.push("/admin/tests");
      router.refresh();
    } catch (caught) {
      setMessage(caught instanceof ApiError ? caught.message : "The draft could not be deleted.");
      setPending(false);
      setConfirmingDelete(false);
    }
  }

  return (
    <div className="builder-toolbar">
      <div className="save-status" role="status">
        <span className={message?.includes("failed") || message?.includes("could not") ? "save-status-error" : ""}>
          <CheckIcon className="size-4" /> {pending || deleting ? "Working…" : published ? "Published · frozen" : "Draft ready"}
        </span>
        {message ? <p>{message}</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => act("validate")} disabled={pending || deleting} className="btn btn-secondary">Validate</button>
        {published ? (
          <button onClick={() => act("clone")} disabled={pending || deleting} className="btn btn-primary">Clone to draft</button>
        ) : status === "DRAFT" ? (
          <button onClick={() => act("publish")} disabled={pending || deleting} className="btn btn-primary">Publish version</button>
        ) : null}
        {status === "DRAFT" ? (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            disabled={pending || deleting}
            className="btn btn-danger-ghost ml-2"
          >
            Delete draft
          </button>
        ) : null}
      </div>
      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this draft?"
        description="All unpublished edits in this draft version will be removed. Published versions and previous attempts will not be affected."
        confirmLabel="Delete draft"
        pending={pending || deleting}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void removeDraft()}
      />
    </div>
  );
}
