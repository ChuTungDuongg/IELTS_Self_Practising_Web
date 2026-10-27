"use client";
import type { ReactNode } from "react";
import type { Classroom } from "@/lib/api/classrooms";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useLmsText } from "./messages";

export function ClassroomHeader({ classroom, management, onManage, onCreate, canCreate }: { classroom: Classroom; management?: ReactNode; onManage?: () => void; onCreate: () => void; canCreate: boolean }) {
  const { lt } = useLmsText(), { t } = useTranslation();
  return <header className="classroom-header">
    <div><h1>{classroom.name}</h1><p className="classroom-meta">{lt("teacher")}: {classroom.teacher_name ?? "—"} · {classroom.active_member_count ?? "—"} {lt("students")} · {t(classroom.status === "ACTIVE" ? "classroom.active" : "classroom.archived")}</p>{classroom.description ? <p className="classroom-description">{classroom.description}</p> : null}</div>
    <div className="classroom-header-actions">{canCreate ? <button type="button" className="btn btn-primary" onClick={onCreate}>{lt("create")}</button> : null}
      {management ? <details className="classroom-menu"><summary>{lt("manage")}</summary><div>{onManage ? <button type="button" className="classroom-text-button" onClick={onManage}>{lt("settings")}</button> : null}{management}</div></details> : null}
    </div>
  </header>;
}
