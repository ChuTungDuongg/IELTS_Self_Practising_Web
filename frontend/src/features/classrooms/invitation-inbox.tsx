"use client";

import { acceptInvitation, declineInvitation, type ClassroomInvitation } from "@/lib/api/classrooms";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ResourceAction } from "./resource-action";
export function InvitationInbox({ invitations }: {
  invitations: ClassroomInvitation[];
}) {
  const { t } = useTranslation();
  const pending = invitations.filter(item => item.status === "PENDING");
  return <section className="surface-card p-5 mb-6" aria-label={t("classroom.invitations")}>
    <h2 className="section-title">{t("classroom.invitations")}</h2>
    {pending.length ? <ul>{pending.map(item => <li key={item.id} className="border-t border-[var(--line)] py-3">
      <p>{t("classroom.invited", { name: item.classroom_name })}</p>
      <div className="flex gap-2 mt-2">
        <ResourceAction action={() => acceptInvitation(item.id)}>{t("classroom.accept")}</ResourceAction>
        <ResourceAction action={() => declineInvitation(item.id)}>{t("classroom.decline")}</ResourceAction>
      </div>
    </li>)}</ul> : <p>{t("classroom.noInvites")}</p>}
  </section>;
}
