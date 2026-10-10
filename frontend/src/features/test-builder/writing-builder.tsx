"use client";

import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PlusIcon } from "@/components/ui/icons";
import { assetContentUrl, uploadAsset } from "@/lib/api/assets";
import {
  createWritingModule,
  deleteModule,
  updateWritingTask,
  type BuilderVersion,
  type BuilderWritingTask,
  type WritingTaskUpdate,
} from "@/lib/api/builder";
import { ApiError } from "@/lib/api/client";
import { builderPreviewPath } from "@/lib/routes";
import { useBuilderAutosave, useBuilderLifecycle } from "./builder-lifecycle";
import { AutosaveLink } from "./autosave-link";
import { ModuleDurationEditor } from "./module-duration-editor";
import { taskOneTypes, taskTwoTypes, type WritingTaskType } from "@/features/writing/task-types";

type TaskDraft = {
  prompt: string;
  taskType: WritingTaskType | null;
  imageAssetId: string | null;
  imageAsset: BuilderWritingTask["image_asset"];
  minimumWords: number | null;
  durationMinutes: number | null;
};

function toDraft(task: BuilderWritingTask): TaskDraft {
  return {
    prompt: task.prompt,
    taskType: task.task_type ?? null,
    imageAssetId: task.image_asset_id,
    imageAsset: task.image_asset,
    minimumWords: task.minimum_recommended_words,
    durationMinutes: task.recommended_duration_seconds === null
      ? null
      : task.recommended_duration_seconds / 60,
  };
}

function toPayload(draft: TaskDraft): Omit<WritingTaskUpdate, "expected_revision"> {
  return {
    prompt: draft.prompt,
    task_type: draft.taskType,
    image_asset_id: draft.imageAssetId,
    minimum_recommended_words: draft.minimumWords,
    recommended_duration_seconds: draft.durationMinutes === null
      ? null
      : Math.round(draft.durationMinutes * 60),
  };
}

export function WritingBuilder({ version }: { version: BuilderVersion }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { beginDelete, deleting, transitioning, flushAutosaves, runAutosave, runMutation } = useBuilderLifecycle();
  const writing = version.modules.find((item) => item.module_type === "WRITING");
  const [savedTasks, setSavedTasks] = useState<Record<string, BuilderWritingTask>>({});
  const savedTasksRef = useRef(savedTasks);
  const tasks = useMemo(
    () => [...(writing?.writing_tasks ?? [])].map((task) => {
      const saved = savedTasks[task.id];
      return saved && saved.revision > task.revision ? saved : task;
    }).sort((a, b) => a.order_index - b.order_index),
    [writing, savedTasks],
  );
  const [drafts, setDrafts] = useState<Record<string, TaskDraft>>(() =>
    Object.fromEntries(tasks.map((task) => [task.id, toDraft(task)])),
  );
  const draftsRef = useRef(drafts);
  const revisions = useRef<Record<string, number>>(Object.fromEntries(tasks.map((task) => [task.id, task.revision])));
  const savedPayloads = useRef<Record<string, string>>(Object.fromEntries(tasks.map((task) => [task.id, JSON.stringify(toPayload(toDraft(task)))])));
  const conflictRef = useRef(false);
  useLayoutEffect(() => { draftsRef.current = drafts; }, [drafts]);
  useLayoutEffect(() => {
    let nextDrafts = draftsRef.current;
    for (const task of tasks) {
      if (!(task.id in nextDrafts)) nextDrafts = { ...nextDrafts, [task.id]: toDraft(task) };
      if (!(task.id in revisions.current)) revisions.current[task.id] = task.revision;
      if (!(task.id in savedPayloads.current)) savedPayloads.current[task.id] = JSON.stringify(toPayload(toDraft(task)));
    }
    if (nextDrafts !== draftsRef.current) {
      draftsRef.current = nextDrafts;
      setDrafts(nextDrafts);
    }
  }, [tasks]);
  const [message, setMessage] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const messageText = typeof message === "string" ? message : message ? t(message.message, message.params) : null;
  const [error, setError] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const errorText = typeof error === "string" ? error : error ? t(error.message, error.params) : null;
  const [conflict, setConflict] = useState(false);
  const [uploadingTaskId, setUploadingTaskId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const draftsValid = Object.values(drafts).every((draft) => draft.prompt.length <= 20_000
    && (draft.minimumWords === null || (draft.minimumWords >= 1 && draft.minimumWords <= 5000))
    && (draft.durationMinutes === null || (draft.durationMinutes >= 1 && draft.durationMinutes <= 240)));
  const autosaveKey = `writing-module:${writing?.id ?? "new"}`;
  async function persistTask(task: BuilderWritingTask, draft: TaskDraft): Promise<BuilderWritingTask> {
    if (conflictRef.current) throw new ApiError("DRAFT_REVISION_CONFLICT", "Reload the latest version before saving.", 409);
    const content = toPayload(draft);
    const serialized = JSON.stringify(content);
    if (savedPayloads.current[task.id] === serialized) return savedTasksRef.current[task.id] ?? task;
    try {
      const saved = await updateWritingTask(task.id, { ...content, expected_revision: revisions.current[task.id] });
      revisions.current[task.id] = saved.revision;
      savedPayloads.current[task.id] = JSON.stringify(toPayload(toDraft(saved)));
      savedTasksRef.current = { ...savedTasksRef.current, [saved.id]: saved };
      setSavedTasks(savedTasksRef.current);
      return saved;
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "DRAFT_REVISION_CONFLICT") {
        conflictRef.current = true;
        setConflict(true);
      }
      throw reason;
    }
  }
  const { saveNow } = useBuilderAutosave({
    resourceKey: autosaveKey,
    value: drafts,
    enabled: Boolean(writing),
    valid: draftsValid,
    save: async (values) => {
      if (!writing) return values;
      const canonical = { ...values };
      for (const task of tasks) {
        canonical[task.id] = toDraft(await persistTask(task, values[task.id] ?? toDraft(task)));
      }
      return canonical;
    },
    onSaved: (canonical, _submitted, unchanged) => {
      router.refresh();
      if (unchanged) {
        draftsRef.current = canonical;
        setDrafts(canonical);
        return canonical;
      }
    },
  });

  async function mutate(action: () => Promise<unknown>, success: TranslationKey) {
    setError(null);
    setMessage(null);
    try {
      if (!(await flushAutosaves())) throw new Error("Unsaved draft changes must be resolved before continuing.");
      await runMutation(action);
      setMessage({ message: success });
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : { message: "builder.writingChangeFailed" });
      throw reason;
    }
  }

  if (!writing) {
    return <section className="reading-empty writing-empty">
      <div className="listening-orb" />
      <h2>{t("builder.buildWriting")}</h2>
      <p>{t("builder.writingCreateHelp")}</p>
      <button
        className="btn btn-writing mt-5"
        disabled={deleting || transitioning}
        onClick={() => void mutate(() => createWritingModule(version.id), "builder.writingCreated")}
      ><PlusIcon className="size-4" /> {t("builder.createWriting")}</button>
      {error ? <p role="alert" className="notice notice-error mt-4">{errorText}</p> : null}
    </section>;
  }
  const writingModule = writing;

  function updateDraft(taskId: string, change: Partial<TaskDraft>): TaskDraft {
    const nextDraft = { ...draftsRef.current[taskId], ...change };
    const nextDrafts = { ...draftsRef.current, [taskId]: nextDraft };
    draftsRef.current = nextDrafts;
    setDrafts(nextDrafts);
    return nextDraft;
  }

  async function save(task: BuilderWritingTask, nextDraft = draftsRef.current[task.id]) {
    setError(null);
    setMessage(null);
    try {
      const saved = await runAutosave(autosaveKey, () => persistTask(task, nextDraft));
      if (JSON.stringify(toPayload(draftsRef.current[task.id])) === JSON.stringify(toPayload(nextDraft))) {
        updateDraft(task.id, toDraft(saved));
      }
      setMessage({ message: "builder.taskSaved", params: { number: task.task_number } });
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : { message: "builder.writingTaskFailed" });
      throw reason;
    }
  }

  async function upload(task: BuilderWritingTask, file: File) {
    setUploadingTaskId(task.id);
    setError(null);
    try {
      const asset = await uploadAsset("images", version.id, file);
      const nextDraft = updateDraft(task.id, {
        imageAssetId: asset.id,
        imageAsset: asset,
      });
      await save(task, nextDraft);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : { message: "builder.writingImageFailed" });
    } finally {
      setUploadingTaskId(null);
    }
  }

  async function removeImage(task: BuilderWritingTask) {
    const previousImage = {
      imageAssetId: draftsRef.current[task.id].imageAssetId,
      imageAsset: draftsRef.current[task.id].imageAsset,
    };
    const nextDraft = updateDraft(task.id, {
      imageAssetId: null,
      imageAsset: null,
    });
    try {
      await save(task, nextDraft);
    } catch {
      updateDraft(task.id, previousImage);
    }
  }

  async function deleteWritingModule() {
    setError(null);
    try {
      await beginDelete(() => deleteModule(writingModule.id));
      setConfirmingDelete(false);
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : { message: "builder.writingDeleteFailed" });
    }
  }

  return <fieldset disabled={deleting || transitioning} className="contents">
    <section className="writing-builder">
      <div className="section-header">
        <div><p className="page-eyebrow writing-eyebrow">{t("builder.moduleWriting")}</p><h2>{t("builder.editorWriting")}</h2><p>{t("builder.writingHelp")}</p></div>
        <div className="flex flex-wrap gap-2"><AutosaveLink href={builderPreviewPath(version.test_id, version.id, "writing")} className="btn btn-secondary">{t("builder.previewWriting")}</AutosaveLink><span className="module-state">{tasks.filter((task) => drafts[task.id]?.prompt.trim()).length} / 2 {t("builder.promptsReady")}</span><button onClick={() => setConfirmingDelete(true)} className="btn btn-danger-ghost">{t("builder.deleteModule")}</button></div>
      </div>
      {message ? <p role="status" className="notice mt-4">{messageText}</p> : null}
      {error ? <p role="alert" className="notice notice-error mt-4">{errorText}</p> : null}
      {conflict ? <p role="alert" className="notice notice-error mt-4">{t("builder.shortConflict")}<button type="button" className="btn btn-ghost" onClick={() => window.location.reload()}>{t("builder.reload")}</button></p> : null}
      <ModuleDurationEditor module={writingModule} />
      <div className="writing-task-grid">
        {tasks.map((task) => {
          const draft = drafts[task.id] ?? toDraft(task);
          return <fieldset key={task.id} aria-label={t("builder.writingTask", { number: task.task_number })} className="writing-task-card">
            <legend>{t("common.taskNumber", { number: task.task_number })}</legend>
            <p className="section-description">{task.task_number === 1 ? "Describe visual information. One image may be attached." : "Respond to a point of view, argument, or problem. Images are not allowed."}</p>
            <label className="field-label">{t("builder.questionType")}
              <select className="select-field mt-2" value={draft.taskType ?? ""} onChange={(event) => updateDraft(task.id, { taskType: event.target.value ? event.target.value as WritingTaskType : null })}>
                <option value="">{t("common.unclassified")}</option>
                {(task.task_number === 1 ? taskOneTypes : taskTwoTypes).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <label className="field-label">{t("builder.prompt")}<textarea className="textarea-field mt-2" rows={8} value={draft.prompt} onChange={(event) => updateDraft(task.id, { prompt: event.target.value })} /></label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="field-label">{t("builder.minimumWords")}<input className="field mt-2" type="number" min="1" value={draft.minimumWords ?? ""} onChange={(event) => updateDraft(task.id, { minimumWords: event.target.value ? Number(event.target.value) : null })} /></label>
              <label className="field-label">{t("builder.timeMinutes")}<input className="field mt-2" type="number" min="1" value={draft.durationMinutes ?? ""} onChange={(event) => updateDraft(task.id, { durationMinutes: event.target.value ? Number(event.target.value) : null })} /></label>
            </div>
            {task.task_number === 1 ? <div className="writing-image-editor">
              <div>{draft.imageAsset ? <Image unoptimized width={720} height={420} src={assetContentUrl(draft.imageAsset)} alt="Writing Task 1 reference" /> : <p>No Task 1 image attached.</p>}</div>
              <div className="flex flex-wrap gap-2"><label className="btn btn-secondary">{uploadingTaskId === task.id ? "Uploading…" : draft.imageAsset ? "Replace image" : "Upload image"}<input aria-label="Task image" type="file" className="sr-only" accept="image/png,image/jpeg,image/webp" disabled={uploadingTaskId === task.id} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(task, file); }} /></label>{draft.imageAsset ? <button type="button" className="btn btn-danger-ghost" onClick={() => void removeImage(task)}>Remove image</button> : null}</div>
            </div> : null}
            <button type="button" className="btn btn-writing" disabled={!draftsValid || conflict} onClick={() => void saveNow()}>{t("builder.saveTask", { number: task.task_number })}</button>
          </fieldset>;
        })}
      </div>
    </section>
    <ConfirmDialog open={confirmingDelete} title={t("builder.deleteWritingTitle")} description={t("builder.deleteWritingDescription")} confirmLabel={t("builder.deleteWriting")} pending={deleting} onCancel={() => setConfirmingDelete(false)} onConfirm={() => void deleteWritingModule()} />
  </fieldset>;
}
