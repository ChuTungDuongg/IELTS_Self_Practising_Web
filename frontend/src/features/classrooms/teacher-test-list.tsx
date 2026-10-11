"use client";

import Link from "next/link";
import { type TestSummary } from "@/lib/api/schema";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { builderEditPath } from "@/lib/routes";
export function TeacherTestList({ tests, ownerId }: {
  tests: TestSummary[];
  ownerId: string;
}) {
  const { t } = useTranslation();
  return <div className="test-card-grid">{tests.filter(test => test.owner_user_id === ownerId && test.origin === "TEACHER").map(test => {
    const latest = test.versions.find(item => item.status === "DRAFT") ?? test.versions.at(-1);
    return <article key={test.id} className="surface-card p-5">
      <h2>{test.title}</h2>
      <p>{test.description}</p>
      <p>{t("teacher.owned")}{test.archived_at ? ` · ${t("common.archived")}` : ""}</p>{latest ? <Link className="btn btn-primary mt-3" href={builderEditPath(test.id, latest.id, "teacher")}>{t("common.open")}</Link> : null}</article>;
  })}</div>;
}
