"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { questionRegistry } from "@/features/questions/registry";
import { ApiError } from "@/lib/api/client";
import type { BuilderVersion } from "@/lib/api/builder";
import { cloneVersion, deleteDraft, publishVersion, validateVersion } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";
import { BuilderAutosaveStatus, useBuilderLifecycle } from "./builder-lifecycle";

type ValidationIssue = { path: string; message: string };
type ValidationResult = { valid: boolean; errors: ValidationIssue[]; warnings: ValidationIssue[] };

export function VersionActions({ testId, version }: { testId: string; version: BuilderVersion }) {
  const router = useRouter();
  const { beginDelete, deleting, mutating, transitioning, runTransition } = useBuilderLifecycle();
  const [message, setMessage] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const validationPanel = useRef<HTMLElement>(null);
  const { id: versionId, status } = version;
  const published = status === "PUBLISHED";

  function focusValidationPanel() {
    window.setTimeout(() => validationPanel.current?.focus(), 0);
  }

  async function act(action: "validate" | "publish" | "clone") {
    setPending(true);
    setMessage(null);
    setActionError(null);
    try {
      const transition = await runTransition(async () => {
        if (action === "validate" || action === "publish") {
          const result = await validateVersion(versionId);
          setValidation(result);
          if (!result.valid) {
            focusValidationPanel();
            return;
          }
          if (action === "publish") {
            await publishVersion(versionId);
            setMessage("Version published and frozen.");
            router.refresh();
          } else {
            setMessage("Validation complete.");
            focusValidationPanel();
          }
        } else {
          const clone = await cloneVersion(testId, versionId);
          router.push(builderEditPath(testId, clone.id));
          router.refresh();
        }
      });
      if (!transition.ready) {
        setActionError("Fix invalid draft fields or retry the failed save before continuing.");
        focusValidationPanel();
      }
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "The action failed.");
      focusValidationPanel();
    } finally {
      setPending(false);
    }
  }

  async function removeDraft() {
    if (pending || deleting) return;
    setPending(true);
    setMessage(null);
    setActionError(null);
    try {
      await beginDelete(() => deleteDraft(testId, versionId));
      router.push("/admin/tests");
      router.refresh();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "The draft could not be deleted.");
      setPending(false);
      setConfirmingDelete(false);
      focusValidationPanel();
    }
  }

  return (
    <>
      <div className="builder-toolbar">
        <div><BuilderAutosaveStatus />{message ? <p role="status">{message}</p> : null}{pending || deleting ? <p role="status">Working…</p> : published ? <p>Published · frozen</p> : null}</div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => act("validate")} disabled={pending || deleting || mutating || transitioning} className="btn btn-secondary">Validate</button>
          {published ? (
            <button onClick={() => act("clone")} disabled={pending || deleting || mutating || transitioning} className="btn btn-primary">Edit</button>
          ) : status === "DRAFT" ? (
            <button onClick={() => act("publish")} disabled={pending || deleting || mutating || transitioning} className="btn btn-primary">Publish version</button>
          ) : null}
          {status === "DRAFT" ? (
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              disabled={pending || deleting || mutating || transitioning}
              className="btn btn-danger-ghost ml-2"
            >
              Delete draft
            </button>
          ) : null}
        </div>
      </div>

      {validation || actionError ? (
        <section
          ref={validationPanel}
          className={`validation-result-panel ${validation?.errors.length || actionError ? "validation-result-panel-error" : ""}`}
          role={validation?.errors.length || actionError ? "alert" : "status"}
          aria-labelledby="validation-result-title"
          tabIndex={-1}
        >
          <div className="validation-result-heading">
            <div>
              <p className="page-eyebrow">Publish validation</p>
              <h2 id="validation-result-title">
                {actionError ? "The action could not be completed" : validation?.errors.length ? "Cannot publish yet" : "Validation passed"}
              </h2>
            </div>
            {!actionError && validation?.valid ? <span className="validation-ready-badge">No blocking errors</span> : null}
          </div>

          {actionError ? <p className="validation-action-error">{actionError}</p> : null}

          {validation?.errors.length ? (
            <div className="validation-blocking-errors">
              <h3>Blocking errors</h3>
              <div className="validation-issue-list">
                {validation.errors.map((issue, index) => {
                  const context = resolveValidationContext(issue.path, version);
                  return (
                    <article className="validation-issue" key={`${issue.path}-${index}`}>
                      <p className="validation-issue-location">{context.location}</p>
                      {context.subject ? <p className="validation-issue-subject">{context.subject}</p> : null}
                      <p className="validation-issue-message">{issue.message}</p>
                      <code className="validation-issue-path">{issue.path}</code>
                    </article>
                  );
                })}
              </div>
            </div>
          ) : null}

          {validation?.warnings.length ? (
            <div className="validation-recommendations">
              <h3>IELTS readiness</h3>
              <ul>{validation.warnings.map((warning, index) => <li key={`${warning.path}-${index}`}>{warning.message}</li>)}</ul>
              <p>These recommendations do not block publishing.</p>
            </div>
          ) : validation?.valid ? <p className="validation-clean">This version has no blocking validation errors or readiness warnings.</p> : null}
        </section>
      ) : null}

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this draft?"
        description="All unpublished edits in this draft version will be removed. Published versions and previous attempts will not be affected."
        confirmLabel="Delete draft"
        pending={pending || deleting}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void removeDraft()}
      />
    </>
  );
}

function resolveValidationContext(path: string, version: BuilderVersion): { location: string; subject?: string } {
  const [moduleName] = path.split(".");
  const builderModule = version.modules.find((item) => item.module_type.toLowerCase() === moduleName);
  if (!builderModule) return { location: humanizePath(path) };

  const passages = [...builderModule.passages].sort((a, b) => a.order_index - b.order_index);
  const groupId = path.match(/\.question_groups\.([0-9a-f-]+)/i)?.[1];
  const questionNumber = Number(path.match(/\.questions\.(\d+)/)?.[1]);
  const passageId = path.match(/\.passages\.([0-9a-f-]+)/i)?.[1];

  for (const [passageIndex, passage] of passages.entries()) {
    const group = passage.question_groups.find((item) => item.id === groupId)
      ?? passage.question_groups.find((item) => item.questions.some((question) => question.number === questionNumber));
    if (group) {
      return {
        location: `Reading Passage ${passageIndex + 1} · ${passage.title}`,
        subject: `${questionRegistry[group.question_type].label} · ${questionRange(group.questions.map((question) => question.number))}`,
      };
    }
    if (passage.id === passageId) {
      return { location: `Reading Passage ${passageIndex + 1} · ${passage.title}`, subject: "Passage content" };
    }
  }

  if (moduleName === "reading") return { location: "Reading module", subject: humanizePath(path) };
  if (moduleName === "listening") return { location: "Listening module", subject: humanizePath(path) };
  return { location: humanizePath(path) };
}

function questionRange(numbers: number[]): string {
  if (!numbers.length) return "No questions";
  const minimum = Math.min(...numbers);
  const maximum = Math.max(...numbers);
  return minimum === maximum ? `Q${minimum}` : `Q${minimum}–${maximum}`;
}

function humanizePath(path: string): string {
  return path
    .split(".")
    .filter((part) => !/^[0-9a-f-]{20,}$/i.test(part))
    .map((part) => part.replaceAll("_", " "))
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" · ");
}
