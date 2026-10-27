"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { inviteStudent, cancelInvitation, removeMember, archiveClassroom, restoreClassroom, leaveClassroom, type Classroom, type ClassroomInvitation, type ClassroomMember } from "@/lib/api/classrooms";
import { ApiError } from "@/lib/api/client";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ResourceAction } from "./resource-action";
import { ClassroomForm } from "./classroom-form";
export function ClassroomMembershipActions({ classroom, isAdmin, canManage, isStaff = false }: {
  classroom: Classroom;
  isAdmin: boolean;
  canManage: boolean;
  isStaff?: boolean;
}) {
  const { t } = useTranslation();
  return <div className="classroom-toolbar">{canManage && classroom.status === "ACTIVE" ? <ResourceAction action={() => archiveClassroom(classroom.id)}>{t("common.archive")}</ResourceAction> : isAdmin && classroom.status === "ARCHIVED" ? <ResourceAction action={() => restoreClassroom(classroom.id)}>{t("common.restore")}</ResourceAction> : null}{!canManage && !isStaff && classroom.status === "ACTIVE" ? <ResourceAction action={() => leaveClassroom(classroom.id)}>{t("classroom.leave")}</ResourceAction> : null}</div>;
}
export function ClassroomManagement({ classroom, invitations, members }: {
  classroom: Classroom;
  invitations: ClassroomInvitation[];
  members: ClassroomMember[];
  canEditClassroom?: boolean;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = classroom.status === "ACTIVE";
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending)
      return;
    const formElement = event.currentTarget;
    const email = String(new FormData(formElement).get("email"));
    setPending(true);
    setError(null);
    try {
      await inviteStudent(classroom.id, email);
      formElement.reset();
      router.refresh();
    }
    catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("governance.error"));
    }
    finally {
      setPending(false);
    }
  }
  return <>
    {active ? <>
      {classroom.capabilities?.includes("classroom.manage") !== false ? <ClassroomForm classroom={classroom} /> : null}
      <form onSubmit={invite} className="surface-card p-5 mb-6">
        <h2>{t("classroom.invite")}</h2>
        <p>{t("classroom.pendingEmail")}</p>
        <label className="field-label mt-3">{t("classroom.email")}<input className="field" name="email" type="email" required />
        </label>
        <button className="btn btn-primary mt-3" disabled={pending}>{t("classroom.invite")}</button>{error ? <p role="alert">{error}</p> : null}</form>
    </> : null}
    <section className="surface-card p-5 mb-6" aria-label={t("classroom.invitations")}>
      <h2>{t("classroom.invitations")}</h2>
      <ul>{invitations.map(item => <li key={item.id} className="py-2">
        <p>{item.invited_email} · {t(item.status === "PENDING" ? "moderation.pending" : item.status === "ACCEPTED" ? "classroom.accept" : item.status === "DECLINED" ? "classroom.decline" : "moderation.cancelled")}</p>{active && item.status === "PENDING" ? <ResourceAction action={() => cancelInvitation(item.id)}>{t("classroom.cancel")}</ResourceAction> : null}</li>)}</ul>
    </section>
    <section className="surface-card p-5 mb-6" aria-label={t("classroom.members")}>
      <h2>{t("classroom.members")}</h2>{members.length ? <ul>{members.map(member => <li key={member.id} className="py-2">
        <p>{member.display_name} · {member.email}{member.left_at ? ` · ${t("classroom.left")}` : ""}</p>{active && !member.left_at ? <ResourceAction action={() => removeMember(classroom.id, member.user_id)}>{t("classroom.remove")}</ResourceAction> : null}</li>)}</ul> : <p>{t("classroom.noMembers")}</p>}</section>
  </>;
}
