"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createAssignment } from "@/lib/api/classrooms";
import type { TestSummary } from "@/lib/api/schema";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ScheduleFields } from "./scheduling/schedule-fields";
import { serializeSchedule } from "@/lib/api/assignment-scheduling";
import { scheduleError, useScheduleText } from "./scheduling/messages";
export function AssignmentForm({ classroomId, tests }: {
  classroomId: string;
  tests: TestSummary[];
}) {
  const { t } = useTranslation();
  const { st } = useScheduleText();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = useRef(false);
  const versions = tests.filter(test => !test.archived_at).flatMap(test => test.versions.filter(version => version.status === "PUBLISHED").map(version => ({ id: version.id, label: `${test.title} · ${t("common.versionNumber", { number: version.version_number })}` })));
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running.current)
      return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    let schedule;
    try { schedule = serializeSchedule(form); } catch { setError(st("invalid")); return; }
    running.current = true;
    setPending(true);
    setError(null);
    try {
      await createAssignment(classroomId, {
        ...schedule,
        test_version_id: String(form.get("version")),
        title: String(form.get("title") ?? "").trim() || null,
        note: String(form.get("note") ?? "").trim() || null
      });
      formElement.reset();
      router.refresh();
    }
    catch (caught) {
      setError(scheduleError(caught, st));
    }
    finally {
      running.current = false;
      setPending(false);
    }
  }
  return <form onSubmit={submit} className="surface-card p-5 mb-6">
    <h2>{t("assignment.create")}</h2>
    <label className="field-label mt-3">{t("assignment.version")}<select required name="version" className="select-field">
      <option value="">—</option>{versions.map(version => <option key={version.id} value={version.id}>{version.label}</option>)}</select>
    </label>
    <label className="field-label mt-3">{t("assignment.name")}<input className="field" name="title" maxLength={240} />
    </label>
    <label className="field-label mt-3">{t("assignment.note")}<textarea className="field" name="note" maxLength={2000} />
    </label>
    <details><summary>{st("schedule")}</summary><ScheduleFields /></details>
    <button className="btn btn-primary mt-3" disabled={pending || !versions.length}>{t("assignment.create")}</button>{error ? <p role="alert">{error}</p> : null}</form>;
}
