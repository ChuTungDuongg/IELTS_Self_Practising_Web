"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/features/auth/auth-provider";
import { reviewModeration, type ModerationRequest } from "@/lib/api/content-governance";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ResourceAction } from "./resource-action";
import { moderationTranslationKeys } from "@/lib/i18n/translations";
export function ModerationFilters({ status }: {
  status: ModerationRequest["status"];
}) {
  const { t } = useTranslation();
  const statuses = ["PENDING", "APPROVED", "REJECTED", "CANCELLED", "REVOKED"] as const;
  return <nav className="flex flex-wrap gap-2 mb-5" aria-label={t("moderation.title")}>
    {statuses.map(item => <Link key={item} className="btn btn-secondary" aria-current={item === status ? "page" : undefined} href={`/admin/moderation?status=${item}`}>{t(moderationTranslationKeys[item])}</Link>)}
  </nav>;
}
export function ModerationActions({ request }: {
  request: ModerationRequest;
}) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const [note, setNote] = useState("");
  if (user?.role !== "ADMIN" || !["PENDING", "APPROVED"].includes(request.status))
    return null;
  return <div className="surface-card p-5 mt-5">
    <label className="field-label">{t("moderation.note")}<textarea className="field" maxLength={2000} value={note} onChange={event => setNote(event.target.value)} />
    </label>
    <div className="flex gap-2 mt-3">
      {request.status === "PENDING" ? <>
        <ResourceAction action={() => reviewModeration(request.id, "approve", note)}>{t("moderation.approve")}</ResourceAction>
        <ResourceAction action={() => reviewModeration(request.id, "reject", note)}>{t("moderation.reject")}</ResourceAction>
      </> : <ResourceAction action={() => reviewModeration(request.id, "revoke", note)}>{t("moderation.revoke")}</ResourceAction>}
    </div>
  </div>;
}
