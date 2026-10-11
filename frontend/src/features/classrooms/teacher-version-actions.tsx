"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { cloneVersion } from "@/lib/api/tests";
import { cancelModeration, submitModeration, type ModerationRequest } from "@/lib/api/content-governance";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moderationTranslationKeys } from "@/lib/i18n/translations";
import { useBuilderLifecycle, BuilderAutosaveStatus } from "@/features/test-builder/builder-lifecycle";
import { builderEditPath } from "@/lib/routes";
import type { BuilderVersion } from "@/lib/api/builder";
export function TeacherVersionActions({ version, requests }: {
  version: BuilderVersion;
  requests: ModerationRequest[];
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const { runTransition, mutating, transitioning } = useBuilderLifecycle();
  const [scope, setScope] = useState<"CLASSROOM" | "PUBLIC">("CLASSROOM");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = requests.some(item => item.status === "PENDING");
  async function act(action: () => Promise<unknown>) {
    if (pending)
      return;
    setPending(true);
    setError(null);
    try {
      const result = await runTransition(action);
      if (!result.ready)
        setError(t("builder.fixDraft"));
      else
        router.refresh();
    }
    catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("governance.error"));
    }
    finally {
      setPending(false);
    }
  }
  return <section className="surface-card p-5 mb-5" aria-label={t("moderation.title")}>
    <BuilderAutosaveStatus />
    <h2>{t("moderation.title")}</h2>
    <p>{t("moderation.requireReview")}</p>{locked ? <p className="notice">{t("moderation.locked")}</p> : null}
    <ul>{requests.map(item => <li key={item.id} className="py-2">
      <strong>{t(item.scope === "PUBLIC" ? "moderation.public" : "moderation.classroom")} · {t(moderationTranslationKeys[item.status])}</strong>{item.review_note || item.revoke_reason ? <p>{item.review_note ?? item.revoke_reason}</p> : null}{item.status === "PENDING" ? <button className="btn btn-ghost" disabled={pending} onClick={() => void act(() => cancelModeration(item.id))}>{t("moderation.cancel")}</button> : null}</li>)}</ul>
    {version.status !== "ARCHIVED" ? <div className="flex flex-wrap gap-3 items-end">
      <label className="field-label">{t("moderation.title")}<select className="select-field" value={scope} onChange={event => setScope(event.target.value as "CLASSROOM" | "PUBLIC")}>
        <option value="CLASSROOM">{t("moderation.classroom")}</option>
        <option value="PUBLIC">{t("moderation.public")}</option>
      </select>
      </label>
      <label className="field-label flex-1">{t("moderation.submitNote")}<input className="field" maxLength={2000} value={note} onChange={event => setNote(event.target.value)} />
      </label>
      <button className="btn btn-primary" disabled={pending || mutating || transitioning || requests.some(item => item.scope === scope && ["PENDING", "APPROVED"].includes(item.status))} onClick={() => void act(() => submitModeration(version.id, scope, note))}>{t("moderation.request")}</button>
    </div> : null}
    {version.status !== "DRAFT" ? <button className="btn btn-secondary mt-3" disabled={pending} onClick={() => void act(async () => {
      const clone = await cloneVersion(version.test_id, version.id);
      router.push(builderEditPath(version.test_id, clone.id, "teacher"));
    })}>{t("common.edit")}</button> : null}
    {error ? <p role="alert" className="notice notice-error mt-3">{error}</p> : null}
  </section>;
}
