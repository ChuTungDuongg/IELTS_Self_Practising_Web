"use client";
import type { ReactNode } from "react";
import type { Classroom } from "@/lib/api/classrooms";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useLmsText } from "./messages";
import { ActionMenu } from "./action-menu";

export function ClassroomHeader({ classroom, observer = false, management, onManage, onCreate, canCreate, contentActions }: { classroom: Classroom; observer?: boolean; management?: ReactNode; onManage?: () => void; onCreate: () => void; canCreate: boolean; contentActions?: { label: string; action: () => void }[] }) {
  const { lt, locale } = useLmsText(), { t } = useTranslation();
  return <header className="classroom-header">
    <div><h1>{classroom.name}</h1><p className="classroom-meta">{lt("teacher")}: {classroom.teacher_name ?? "—"} · {classroom.active_member_count ?? "—"} {lt("students")} · {t(classroom.status === "ACTIVE" ? "classroom.active" : "classroom.archived")}</p>{classroom.description ? <p className="classroom-description">{classroom.description}</p> : null}</div>
    <div className="classroom-header-actions">{observer ? <p className="classroom-meta classroom-observer" role="status">{locale === "vi" ? "Chế độ dự thính · Chỉ xem" : "Observer mode · Read only"}</p> : null}{!observer && (canCreate || contentActions?.length) ? <ActionMenu label={lt("create")} primary>{contentActions?.map(item => <button type="button" key={item.label} onClick={item.action}>{item.label}</button>)}{canCreate ? <button type="button" onClick={onCreate}>{lt("newAssignment")}</button> : null}</ActionMenu> : null}
      {!observer && management ? <ActionMenu label={lt("manage")}>{onManage ? <button type="button" className="classroom-text-button" onClick={onManage}>{lt("settings")}</button> : null}{management}</ActionMenu> : null}
    </div>
  </header>;
}
