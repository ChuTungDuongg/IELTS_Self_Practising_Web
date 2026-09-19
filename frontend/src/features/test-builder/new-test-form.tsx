"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { createTest } from "@/lib/api/tests";

export function NewTestForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const test = await createTest({
        title: String(form.get("title") ?? ""),
        description: String(form.get("description") ?? ""),
      });
      router.push(`/admin/tests/${test.id}`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The test could not be created.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="surface-card max-w-2xl p-7 sm:p-8">
      <div className="mb-7 border-b border-[var(--line)] pb-5">
        <h2 className="section-title">Test details</h2>
        <p className="section-description">Use a clear title that will still make sense when multiple versions exist.</p>
      </div>
      <label className="field-label">
        Test title
        <input name="title" required maxLength={240} placeholder="e.g. Reading Practice Set 01" className="field" />
      </label>
      <label className="field-label mt-5">
        Description <span className="font-normal text-[var(--muted)]">(optional)</span>
        <textarea name="description" rows={4} placeholder="Add a short internal description…" className="field resize-y" />
      </label>
      {error ? <p role="alert" className="notice notice-error mt-5">{error}</p> : null}
      <div className="mt-7 flex justify-end border-t border-[var(--line)] pt-5">
      <button disabled={pending} className="btn btn-primary">
        {pending ? "Creating…" : "Create draft"}
      </button>
      </div>
    </form>
  );
}
