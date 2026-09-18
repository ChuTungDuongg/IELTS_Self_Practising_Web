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
    <form onSubmit={submit} className="max-w-2xl space-y-5 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6">
      <label className="block">
        <span className="text-sm font-medium">Title</span>
        <input name="title" required maxLength={240} className="mt-2 w-full rounded-md border border-[var(--line)] px-3 py-2.5" />
      </label>
      <label className="block">
        <span className="text-sm font-medium">Description</span>
        <textarea name="description" rows={4} className="mt-2 w-full resize-y rounded-md border border-[var(--line)] px-3 py-2.5" />
      </label>
      {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
      <button disabled={pending} className="rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
        {pending ? "Creating…" : "Create draft"}
      </button>
    </form>
  );
}
