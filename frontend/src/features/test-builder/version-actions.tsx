"use client";

import type { TranslationFunction, TranslationKey, TranslationParams } from "@/lib/i18n/types";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { questionRegistry } from "@/features/questions/registry";
import { groupQuestionRange, questionNumbers } from "@/features/questions/numbering";
import { ApiError } from "@/lib/api/client";
import type { BuilderVersion } from "@/lib/api/builder";
import { cloneVersion, deleteDraft, publishVersion, validateVersion } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";
import { BuilderAutosaveStatus, useBuilderLifecycle } from "./builder-lifecycle";

type ValidationIssue = { path: string; message: string };
type ValidationResult = { valid: boolean; errors: ValidationIssue[]; warnings: ValidationIssue[] };

export function VersionActions({ testId, version }: { testId: string; version: BuilderVersion }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { beginDelete, deleting, mutating, transitioning, runTransition } = useBuilderLifecycle();
  const [message, setMessage] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const messageText = typeof message === "string" ? message : message ? t(message.message, message.params) : null;
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [actionError, setActionError] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const actionErrorText = typeof actionError === "string" ? actionError : actionError ? t(actionError.message, actionError.params) : null;
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
            setMessage({ message: "builder.publishedFrozen" });
            router.refresh();
          } else {
            setMessage({ message: "builder.validationComplete" });
            focusValidationPanel();
          }
        } else {
          const clone = await cloneVersion(testId, versionId);
          router.push(builderEditPath(testId, clone.id));
          router.refresh();
        }
      });
      if (!transition.ready) {
        setActionError({ message: "builder.fixDraft" });
        focusValidationPanel();
      }
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : { message: "builder.actionFailed" });
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
      setActionError(caught instanceof ApiError ? caught.message : { message: "builder.deleteDraftFailed" });
      setPending(false);
      setConfirmingDelete(false);
      focusValidationPanel();
    }
  }

  return (
    <>
      <div className="builder-toolbar">
        <div><BuilderAutosaveStatus />{message ? <p role="status">{messageText}</p> : null}{pending || deleting ? <p role="status">{t("common.working")}</p> : published ? <p>{t("builder.frozenStatus")}</p> : null}</div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => act("validate")} disabled={pending || deleting || mutating || transitioning} className="btn btn-secondary">{t("builder.validate")}</button>
          {published ? (
            <button onClick={() => act("clone")} disabled={pending || deleting || mutating || transitioning} className="btn btn-primary">{t("common.edit")}</button>
          ) : status === "DRAFT" ? (
            <button onClick={() => act("publish")} disabled={pending || deleting || mutating || transitioning} className="btn btn-primary">{t("builder.publish")}</button>
          ) : null}
          {status === "DRAFT" ? (
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              disabled={pending || deleting || mutating || transitioning}
              className="btn btn-danger-ghost ml-2"
            >
              {t("builder.deleteDraft")}
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
              <p className="page-eyebrow">{t("builder.publishValidation")}</p>
              <h2 id="validation-result-title">
                {actionError ? t("builder.actionIncomplete") : validation?.errors.length ? t("builder.cannotPublish") : t("builder.valid")}
              </h2>
            </div>
            {!actionError && validation?.valid ? <span className="validation-ready-badge">{t("builder.noBlocking")}</span> : null}
          </div>

          {actionError ? <p className="validation-action-error">{actionErrorText}</p> : null}

          {validation?.errors.length ? (
            <div className="validation-blocking-errors">
              <h3>{t("builder.blocking")}</h3>
              <div className="validation-issue-list">
                {validation.errors.map((issue, index) => {
                  const context = resolveValidationContext(issue.path, version, t);
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
              <h3>{t("builder.readiness")}</h3>
              <ul>{validation.warnings.map((warning, index) => <li key={`${warning.path}-${index}`}>{warning.message}</li>)}</ul>
              <p>{t("builder.recommendations")}</p>
            </div>
          ) : validation?.valid ? <p className="validation-clean">{t("builder.clean")}</p> : null}
        </section>
      ) : null}

      <ConfirmDialog
        open={confirmingDelete}
        title={t("builder.deleteDraftTitle")}
        description={t("builder.deleteDraftDescription")}
        confirmLabel={t("builder.deleteDraft")}
        pending={pending || deleting}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void removeDraft()}
      />
    </>
  );
}

function resolveValidationContext(path: string, version: BuilderVersion, t: TranslationFunction): { location: string; subject?: string } {
  const [moduleName] = path.split(".");
  const builderModule = version.modules.find((item) => item.module_type.toLowerCase() === moduleName);
  if (!builderModule) return { location: humanizePath(path) };

  const passages = [...builderModule.passages].sort((a, b) => a.order_index - b.order_index);
  const groupId = path.match(/\.question_groups\.([0-9a-f-]+)/i)?.[1];
  const questionNumber = Number(path.match(/\.questions\.(\d+)/)?.[1]);
  const passageId = path.match(/\.passages\.([0-9a-f-]+)/i)?.[1];

  for (const [passageIndex, passage] of passages.entries()) {
    const group = passage.question_groups.find((item) => item.id === groupId)
      ?? passage.question_groups.find((item) => questionNumbers(item).includes(questionNumber));
    if (group) {
      return {
        location: `${t("builder.readingPassage", { number: passageIndex + 1 })} · ${passage.title}`,
        subject: `${questionRegistry[group.question_type].label} · ${groupQuestionRange(group)}`,
      };
    }
    if (passage.id === passageId) {
      return { location: `${t("builder.readingPassage", { number: passageIndex + 1 })} · ${passage.title}`, subject: t("builder.passageContent") };
    }
  }

  for (const [partIndex, part] of [...builderModule.listening_parts].sort((a, b) => a.order_index - b.order_index).entries()) {
    const group = part.question_groups.find((item) => item.id === groupId)
      ?? part.question_groups.find((item) => questionNumbers(item).includes(questionNumber));
    if (group) return {
      location: `${t("builder.listeningSection", { number: partIndex + 1 })} · ${part.title}`,
      subject: `${questionRegistry[group.question_type].label} · ${groupQuestionRange(group)}`,
    };
  }

  if (moduleName === "reading") return { location: t("builder.moduleReading"), subject: humanizePath(path) };
  if (moduleName === "listening") return { location: t("builder.moduleListening"), subject: humanizePath(path) };
  return { location: humanizePath(path) };
}

function humanizePath(path: string): string {
  return path
    .split(".")
    .filter((part) => !/^[0-9a-f-]{20,}$/i.test(part))
    .map((part) => part.replaceAll("_", " "))
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" · ");
}
