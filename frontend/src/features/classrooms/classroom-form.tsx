"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createClassroom, updateClassroom, type Classroom } from "@/lib/api/classrooms";
import { ApiError } from "@/lib/api/client";
import { useTranslation } from "@/lib/i18n/locale-provider";
export function ClassroomForm({ classroom, onCreated, returnTo }: {
  classroom?: Classroom;
  onCreated?: (classroom: Classroom) => void;
  returnTo?: string;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending)
      return;
    const form = new FormData(event.currentTarget);
    const input = { name: String(form.get("name")), description: String(form.get("description") ?? "").trim() || null };
    setPending(true);
    setError(null);
    try {
      const saved = classroom ? await updateClassroom(classroom.id, input) : await createClassroom(input);
      if (!classroom && onCreated) onCreated(saved);
      else router.push(returnTo ?? `/teacher/classrooms/${saved.id}`);
      router.refresh();
    }
    catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("governance.error"));
    }
    finally {
      setPending(false);
    }
  }
  return <form onSubmit={submit} className="surface-card p-5 mb-6">
    <label className="field-label">{t("classroom.name")}<input className="field" name="name" required maxLength={200} defaultValue={classroom?.name} />
    </label>
    <label className="field-label mt-3">{t("classroom.description")}<textarea className="field" name="description" maxLength={2000} defaultValue={classroom?.description ?? ""} />
    </label>
    <button className="btn btn-primary mt-3" disabled={pending}>{t(classroom ? "common.save" : "classroom.create")}</button>{error ? <p role="alert" className="notice notice-error">{error}</p> : null}</form>;
}
