"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { cloneVersion, publishVersion, validateVersion } from "@/lib/api/tests";

export function VersionActions({ testId, versionId, published }: { testId: string; versionId: string; published: boolean }) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

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

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        <button onClick={() => act("validate")} disabled={pending} className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm font-semibold">Validate</button>
        {published ? (
          <button onClick={() => act("clone")} disabled={pending} className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white">Clone to draft</button>
        ) : (
          <button onClick={() => act("publish")} disabled={pending} className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white">Publish</button>
        )}
      </div>
      {message ? <p role="status" className="mt-3 max-w-xl text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
