"use client";

import type { Classroom } from "@/lib/api/classrooms";
import { useLocale } from "@/lib/i18n/locale-provider";
export function ClassroomMetadata({ classroom }: { classroom: Classroom }) {
  const { locale } = useLocale();
  if (!classroom.teacher_name && classroom.active_member_count == null) return null;
  return <p className="text-sm text-muted mb-4">
    {classroom.teacher_name ? `${locale === "vi" ? "Giáo viên" : "Teacher"}: ${classroom.teacher_name}` : null}
    {classroom.teacher_name && classroom.active_member_count != null ? " · " : null}
    {classroom.active_member_count != null ? `${new Intl.NumberFormat(locale).format(classroom.active_member_count)} ${locale === "vi" ? "học viên đang tham gia" : "enrolled students"}` : null}
  </p>;
}
