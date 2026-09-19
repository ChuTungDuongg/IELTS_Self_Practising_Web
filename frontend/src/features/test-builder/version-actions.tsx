"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api/client";
import { cloneVersion, deleteDraft, publishVersion, validateVersion } from "@/lib/api/tests";
import { useBuilderLifecycle } from "./builder-lifecycle";

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
    <div>
      <div className="flex flex-wrap gap-2">
        <button onClick={() => act("validate")} disabled={pending || deleting} className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm font-semibold">Validate</button>
        {published ? (
          <button onClick={() => act("clone")} disabled={pending || deleting} className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white">Clone to draft</button>
        ) : status === "DRAFT" ? (
          <button onClick={() => act("publish")} disabled={pending || deleting} className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white">Publish</button>
        ) : null}
        {status === "DRAFT" ? (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            disabled={pending || deleting}
            className="ml-auto rounded-md px-3 py-2 text-sm font-semibold text-red-700 disabled:opacity-50"
          >
            Delete draft
          </button>
        ) : null}
      </div>
      {message ? <p role="status" className="mt-3 max-w-xl text-sm text-[var(--muted)]">{message}</p> : null}
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
