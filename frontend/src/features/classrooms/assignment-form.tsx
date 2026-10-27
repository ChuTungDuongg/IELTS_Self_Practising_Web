"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { assignmentVersion, createAssignment, type AssignmentTarget } from "@/lib/api/classrooms";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";
import { selectedPublishedVersion } from "@/lib/published-version";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { ScheduleFields } from "./scheduling/schedule-fields";
import { serializeSchedule } from "@/lib/api/assignment-scheduling";
import { scheduleError, useScheduleText } from "./scheduling/messages";
import { useContentTranslation } from "./content/content-messages";
import { assignmentUnits } from "./assignment-target";

export function AssignmentForm({ classroomId, tests }: { classroomId: string; tests: TestSummary[] }) {
  const { t } = useTranslation(), { ct } = useContentTranslation(), { st } = useScheduleText(), router = useRouter();
  const [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null);
  const [versionId, setVersionId] = useState(""), [detail, setDetail] = useState<VersionDetail | null>(null), [loadError, setLoadError] = useState(false);
  const [skill, setSkill] = useState(""), [scope, setScope] = useState("FULL_MODULE"), [unitId, setUnitId] = useState("");
  const running = useRef(false);
  const [retry, setRetry] = useState(0);
  const versions = tests.filter(test => !test.archived_at).flatMap(test => { const version = selectedPublishedVersion(test.versions); return version ? [{ id: version.id, label: test.title }] : []; });
  useEffect(() => {
    if (!versionId) return;
    const controller = new AbortController();
    void assignmentVersion(classroomId, versionId, controller.signal).then(value => { if (!controller.signal.aborted) setDetail(value); }).catch(() => { if (!controller.signal.aborted) setLoadError(true); });
    return () => controller.abort();
  }, [classroomId, versionId, retry]);
  const selectedModule = detail?.modules.find(module => module.module_type === skill), units = assignmentUnits(selectedModule);
  const fullMock = ["READING", "LISTENING", "WRITING", "SPEAKING"].every(kind => detail?.modules.some(module => module.module_type === kind && (module.recommended_duration_seconds ?? 0) > 0));
  const unit = units.find(unit => unit.id === unitId);
  const target: AssignmentTarget | null = skill === "FULL_MOCK" && fullMock ? { mode: "FULL_MOCK" } : selectedModule && (scope === "FULL_MODULE" || unit) ? {
    mode: "MODULE", module: selectedModule.module_type, scope: scope as "FULL_MODULE" | "FOCUSED_UNIT", ...(scope === "FOCUSED_UNIT" && unit ? { focused_unit: { kind: unit.kind, id: unit.id } } : {}),
  } : null;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running.current || !target || !detail || detail.id !== versionId) return;
    const element = event.currentTarget, form = new FormData(element);
    let schedule;
    try { schedule = serializeSchedule(form); } catch { setError(st("invalid")); return; }
    running.current = true; setPending(true); setError(null);
    try {
      await createAssignment(classroomId, { ...schedule, test_version_id: versionId, target, title: String(form.get("title") ?? "").trim() || null, note: String(form.get("note") ?? "").trim() || null });
      element.reset(); setVersionId(""); setDetail(null); setSkill(""); setUnitId(""); setScope("FULL_MODULE"); router.refresh();
    } catch (caught) { setError(scheduleError(caught, st)); }
    finally { running.current = false; setPending(false); }
  }
  return <form onSubmit={submit} className="classroom-focused-form classroom-association">
    <h2>{t("assignment.create")}</h2>
    <label className="field-label">{ct("selectTest")}<select required name="version" className="select-field" disabled={pending} value={versionId} onChange={event => { setVersionId(event.target.value); setDetail(null); setLoadError(false); setSkill(""); setScope("FULL_MODULE"); setUnitId(""); setError(null); }}>
      <option value="">—</option>{versions.map(version => <option key={version.id} value={version.id}>{version.label}</option>)}
    </select></label>
    {versionId && !detail ? <div><p role={loadError ? "alert" : "status"}>{ct(loadError ? "targetError" : "targetLoading")}</p>{loadError ? <button className="classroom-text-button" type="button" onClick={() => { setLoadError(false); setRetry(value => value + 1); }}>{ct("retry")}</button> : null}</div> : null}
    {detail ? <>
      <label className="field-label">{ct("selectSkill")}<select className="select-field" required value={skill} disabled={pending} onChange={event => { setSkill(event.target.value); setScope("FULL_MODULE"); setUnitId(""); }}>
        <option value="">—</option>{detail.modules.map(module => <option key={module.id} value={module.module_type}>{t(moduleTranslationKeys[module.module_type])}</option>)}<option value="FULL_MOCK" disabled={!fullMock}>{ct("fullMockTarget")}</option>
      </select></label>
      {!fullMock ? <p className="classroom-meta">{ct("fullMockUnavailable")}</p> : null}
      {selectedModule ? <label className="field-label">{ct("selectScope")}<select className="select-field" value={scope} disabled={pending} onChange={event => { setScope(event.target.value); setUnitId(""); }}><option value="FULL_MODULE">{ct("fullModuleTarget")}</option>{units.length ? <option value="FOCUSED_UNIT">{ct("focusedTarget")}</option> : null}</select></label> : null}
      {selectedModule && scope === "FOCUSED_UNIT" ? <label className="field-label">{ct("selectUnit")}<select className="select-field" required disabled={pending} value={unitId} onChange={event => setUnitId(event.target.value)}><option value="">—</option>{units.map(unit => <option key={unit.id} value={unit.id}>{"partNumber" in unit ? ct("speakingPartTarget", { name: String(unit.partNumber) }) + " / " : ""}{ct(unit.kind, { name: String(unit.number) })}</option>)}</select></label> : null}
    </> : null}
    <label className="field-label">{t("assignment.name")}<input className="field" name="title" maxLength={240} disabled={pending} /></label>
    <label className="field-label">{t("assignment.note")}<textarea className="field" name="note" maxLength={2000} disabled={pending} /></label>
    <details><summary>{st("schedule")}</summary><ScheduleFields /></details>
    <button className="btn btn-primary" disabled={pending || !target}>{pending ? ct("working") : t("assignment.create")}</button>{error ? <p role="alert">{error}</p> : null}
  </form>;
}
