"use client";

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

type TaskDraft = {
  prompt: string;
  imageAssetId: string | null;
  imageAsset: BuilderWritingTask["image_asset"];
  minimumWords: number | null;
  durationMinutes: number | null;
};

function toDraft(task: BuilderWritingTask): TaskDraft {
  return {
    prompt: task.prompt,
    imageAssetId: task.image_asset_id,
    imageAsset: task.image_asset,
    minimumWords: task.minimum_recommended_words,
    durationMinutes: task.recommended_duration_seconds === null
      ? null
      : task.recommended_duration_seconds / 60,
  };
}

function toPayload(draft: TaskDraft): WritingTaskUpdate {
  return {
    prompt: draft.prompt,
    image_asset_id: draft.imageAssetId,
    minimum_recommended_words: draft.minimumWords,
    recommended_duration_seconds: draft.durationMinutes === null
      ? null
      : Math.round(draft.durationMinutes * 60),
  };
}

export function WritingBuilder({ version }: { version: BuilderVersion }) {
  const router = useRouter();
  const { beginDelete, deleting, transitioning, flushAutosaves, runAutosave, runMutation } = useBuilderLifecycle();
  const writing = version.modules.find((item) => item.module_type === "WRITING");
  const tasks = useMemo(
    () => [...(writing?.writing_tasks ?? [])].sort((a, b) => a.order_index - b.order_index),
    [writing],
  );
  const [drafts, setDrafts] = useState<Record<string, TaskDraft>>(() =>
    Object.fromEntries(tasks.map((task) => [task.id, toDraft(task)])),
  );
  const draftsRef = useRef(drafts);
  useLayoutEffect(() => { draftsRef.current = drafts; }, [drafts]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadingTaskId, setUploadingTaskId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const draftsValid = Object.values(drafts).every((draft) => draft.prompt.length <= 20_000
    && (draft.minimumWords === null || (draft.minimumWords >= 1 && draft.minimumWords <= 5000))
    && (draft.durationMinutes === null || (draft.durationMinutes >= 1 && draft.durationMinutes <= 240)));
  const autosaveKey = `writing-module:${writing?.id ?? "new"}`;
  const { saveNow } = useBuilderAutosave({
    resourceKey: autosaveKey,
    value: drafts,
    enabled: Boolean(writing),
    valid: draftsValid,
    save: async (values) => {
      if (!writing) return;
      for (const task of tasks) {
        await updateWritingTask(task.id, toPayload(values[task.id] ?? toDraft(task)));
      }
    },
  });

  async function mutate(action: () => Promise<unknown>, success: string) {
    setError(null);
    setMessage(null);
    try {
      if (!(await flushAutosaves())) throw new Error("Unsaved draft changes must be resolved before continuing.");
      await runMutation(action);
      setMessage(success);
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The Writing change could not be saved.");
      throw reason;
    }
  }

  if (!writing) {
    return <section className="reading-empty writing-empty">
      <div className="listening-orb" />
      <h2>Build the Writing module</h2>
      <p>Create the fixed IELTS Task 1 and Task 2 structure. Prompts and guidance can be completed afterward.</p>
      <button
        className="btn btn-writing mt-5"
        disabled={deleting || transitioning}
        onClick={() => void mutate(() => createWritingModule(version.id), "Writing module created.")}
      ><PlusIcon className="size-4" /> Create Writing module</button>
      {error ? <p role="alert" className="notice notice-error mt-4">{error}</p> : null}
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
      await runAutosave(autosaveKey, () => updateWritingTask(task.id, toPayload(nextDraft)));
      setMessage(`Task ${task.task_number} saved.`);
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The Writing task could not be saved.");
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
      setError(reason instanceof ApiError ? reason.message : "The Writing image could not be uploaded.");
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
      setError(reason instanceof ApiError ? reason.message : "The Writing module could not be deleted.");
    }
  }

  return <fieldset disabled={deleting || transitioning} className="contents">
    <section className="writing-builder">
      <div className="section-header">
        <div><p className="page-eyebrow writing-eyebrow">Writing module</p><h2>Writing Builder</h2><p>Two fixed tasks with server-owned structure and optional visual material for Task 1.</p></div>
        <div className="flex flex-wrap gap-2"><AutosaveLink href={builderPreviewPath(version.test_id, version.id, "writing")} className="btn btn-secondary">Preview Writing</AutosaveLink><span className="module-state">{tasks.filter((task) => drafts[task.id]?.prompt.trim()).length} / 2 prompts ready</span><button onClick={() => setConfirmingDelete(true)} className="btn btn-danger-ghost">Delete module</button></div>
      </div>
      {message ? <p role="status" className="notice mt-4">{message}</p> : null}
      {error ? <p role="alert" className="notice notice-error mt-4">{error}</p> : null}
      <div className="writing-task-grid">
        {tasks.map((task) => {
          const draft = drafts[task.id] ?? toDraft(task);
          return <fieldset key={task.id} aria-label={`Writing Task ${task.task_number}`} className="writing-task-card">
            <legend>Task {task.task_number}</legend>
            <p className="section-description">{task.task_number === 1 ? "Describe visual information. One image may be attached." : "Respond to a point of view, argument, or problem. Images are not allowed."}</p>
            <label className="field-label">Prompt<textarea className="textarea-field mt-2" rows={8} value={draft.prompt} onChange={(event) => updateDraft(task.id, { prompt: event.target.value })} /></label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="field-label">Minimum recommended words<input className="field mt-2" type="number" min="1" value={draft.minimumWords ?? ""} onChange={(event) => updateDraft(task.id, { minimumWords: event.target.value ? Number(event.target.value) : null })} /></label>
              <label className="field-label">Recommended time (minutes)<input className="field mt-2" type="number" min="1" value={draft.durationMinutes ?? ""} onChange={(event) => updateDraft(task.id, { durationMinutes: event.target.value ? Number(event.target.value) : null })} /></label>
            </div>
            {task.task_number === 1 ? <div className="writing-image-editor">
              <div>{draft.imageAsset ? <Image unoptimized width={720} height={420} src={assetContentUrl(draft.imageAsset)} alt="Writing Task 1 reference" /> : <p>No Task 1 image attached.</p>}</div>
              <div className="flex flex-wrap gap-2"><label className="btn btn-secondary">{uploadingTaskId === task.id ? "Uploading…" : draft.imageAsset ? "Replace image" : "Upload image"}<input aria-label="Task image" type="file" className="sr-only" accept="image/png,image/jpeg,image/webp" disabled={uploadingTaskId === task.id} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(task, file); }} /></label>{draft.imageAsset ? <button type="button" className="btn btn-danger-ghost" onClick={() => void removeImage(task)}>Remove image</button> : null}</div>
            </div> : null}
            <button type="button" className="btn btn-writing" disabled={!draftsValid} onClick={() => void saveNow()}>Save Task {task.task_number}</button>
          </fieldset>;
        })}
      </div>
    </section>
    <ConfirmDialog open={confirmingDelete} title="Delete Writing module?" description="Both Writing tasks and their draft prompts will be removed." confirmLabel="Delete Writing module" pending={deleting} onCancel={() => setConfirmingDelete(false)} onConfirm={() => void deleteWritingModule()} />
  </fieldset>;
}
