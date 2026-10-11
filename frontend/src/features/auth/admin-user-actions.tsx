"use client";

import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { updateAdminUser } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "./auth-provider";

export function AdminUserActions({
  userId,
  role,
  isActive,
}: {
  userId: string;
  role: "USER" | "TEACHER" | "ADMIN";
  isActive: boolean;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const errorText = typeof error === "string" ? error : error ? t(error.message, error.params) : null;

  async function update(change: { role?: "USER" | "TEACHER" | "ADMIN"; is_active?: boolean }) {
    setPending(true);
    setError(null);
    try {
      await updateAdminUser(userId, change);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError && caught.code === "TEACHER_HAS_ACTIVE_RESOURCES"
        ? { message: "admin.teacherResourcesConflict" }
        : caught instanceof ApiError ? caught.message : { message: "admin.updateFailed" });
    } finally {
      setPending(false);
    }
  }

  if (user?.role !== "ADMIN") return null;
  return <div className="admin-user-actions" aria-label={t("admin.userAdministration")}>
    {role !== "ADMIN" ? <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => void update({ role: role === "TEACHER" ? "USER" : "TEACHER" })}>{t(role === "TEACHER" ? "admin.demoteTeacher" : "admin.promoteTeacher")}</button> : null}
    <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => void update({ role: role === "ADMIN" ? "USER" : "ADMIN" })}>
      {role === "ADMIN" ? t("admin.demote") : t("admin.promote")}
    </button>
    <button type="button" className="btn btn-ghost" disabled={pending} onClick={() => void update({ is_active: !isActive })}>
      {isActive ? t("admin.deactivateAccount") : t("admin.reactivateAccount")}
    </button>
    {error ? <p role="alert" className="notice">{errorText}</p> : null}
  </div>;
}
