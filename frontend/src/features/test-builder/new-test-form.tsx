"use client";

import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { createTest } from "@/lib/api/tests";

export function NewTestForm() {
  const { t } = useTranslation();
  const router = useRouter();
  const [error, setError] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const errorText = typeof error === "string" ? error : error ? t(error.message, error.params) : null;
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
      setError(caught instanceof ApiError ? caught.message : { message: "builder.createFailed" });
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="surface-card max-w-2xl p-7 sm:p-8">
      <div className="mb-7 border-b border-[var(--line)] pb-5">
        <h2 className="section-title">{t("builder.details")}</h2>
        <p className="section-description">{t("builder.titleHelp")}</p>
      </div>
      <label className="field-label">
        {t("builder.testTitle")}
        <input name="title" required maxLength={240} placeholder={t("builder.titlePlaceholder")} className="field" />
      </label>
      <label className="field-label mt-5">
        {t("common.description")} <span className="font-normal text-[var(--muted)]">{t("common.optional")}</span>
        <textarea name="description" rows={4} placeholder={t("builder.descriptionPlaceholder")} className="field resize-y" />
      </label>
      {error ? <p role="alert" className="notice notice-error mt-5">{errorText}</p> : null}
      <div className="mt-7 flex justify-end border-t border-[var(--line)] pt-5">
      <button disabled={pending} className="btn btn-primary">
        {pending ? t("builder.creating") : t("builder.createDraft")}
      </button>
      </div>
    </form>
  );
}
