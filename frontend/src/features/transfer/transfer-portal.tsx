"use client";

import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useState } from "react";
import Link from "next/link";
import { moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";
import { ApiError } from "@/lib/api/client";
import { exportTests, importTests, type TransferImportResult } from "@/lib/api/transfer";

export type TransferTestOption = {
  id: string;
  title: string;
  latestVersion: number | null;
  states: string[];
  skills: string[];
  archived: boolean;
};

export function TransferPortal({ tests }: { tests: TransferTestOption[] }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<TransferImportResult | null>(null);
  const [error, setError] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const errorText = typeof error === "string" ? error : error ? t(error.message, error.params) : null;

  function toggle(testId: string) {
    setSelected((current) => current.includes(testId) ? current.filter((id) => id !== testId) : [...current, testId]);
  }

  async function download() {
    setExporting(true);
    setError(null);
    try {
      const response = await exportTests(selected);
      const url = URL.createObjectURL(response.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : { message: "transfer.exportFailed" });
    } finally {
      setExporting(false);
    }
  }

  async function upload() {
    if (!file) return;
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      setResult(await importTests(file));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : { message: "transfer.importFailed" });
    } finally {
      setImporting(false);
    }
  }

  return <div className="grid gap-6 lg:grid-cols-2">
    <section className="panel p-6" aria-labelledby="transfer-export-title">
      <p className="page-eyebrow">{t("transfer.machineA")}</p>
      <h2 id="transfer-export-title" className="section-title">{t("transfer.export")}</h2>
      <p className="section-description">{t("transfer.exportHelp")}</p>
      <div className="mt-5 grid gap-3">
        {tests.map((test) => <label key={test.id} className="question-group-card cursor-pointer">
          <input type="checkbox" checked={selected.includes(test.id)} onChange={() => toggle(test.id)} aria-label={t("transfer.select", { title: test.title })} />
          <span className="min-w-0 flex-1"><b className="block">{test.title}</b><small className="text-[var(--muted)]">{test.latestVersion ? t("transfer.latest", { number: test.latestVersion }) : t("builder.noVersions")} · {test.states.map((state) => statusTranslationKeys[state] ? t(statusTranslationKeys[state]) : state).join(" / ") || t("transfer.noState")} · {test.skills.map((skill) => moduleTranslationKeys[skill as keyof typeof moduleTranslationKeys] ? t(moduleTranslationKeys[skill as keyof typeof moduleTranslationKeys]) : skill).join(", ") || t("transfer.noModules")}{test.archived ? t("transfer.archived") : ""}</small></span>
        </label>)}
        {!tests.length ? <p className="notice">{t("transfer.empty")}</p> : null}
      </div>
      <button type="button" className="btn btn-primary mt-5" disabled={!selected.length || exporting} onClick={() => void download()}>{exporting ? t("transfer.exporting") : t("transfer.exportSelected")}</button>
    </section>

    <section className="panel p-6" aria-labelledby="transfer-import-title">
      <p className="page-eyebrow">{t("transfer.machineB")}</p>
      <h2 id="transfer-import-title" className="section-title">{t("transfer.importTitle")}</h2>
      <p className="section-description">{t("transfer.importHelp")}</p>
      <label className="field-label mt-5 block">{t("transfer.chooseZIP")}<input aria-label={t("transfer.packageZIP")} className="field mt-2" type="file" accept=".zip,application/zip" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setResult(null); setError(null); }} /></label>
      <p className="mt-3 text-sm text-[var(--muted)]">{t("transfer.selected", { filename: file?.name ?? t("transfer.none") })}</p>
      <button type="button" className="btn btn-primary mt-5" disabled={!file || importing} onClick={() => void upload()}>{importing ? t("transfer.importing") : t("transfer.import")}</button>
      {result ? <div role="status" className="notice notice-success mt-4"><b>{t(result.imported_tests.length === 1 ? "transfer.importedOne" : "transfer.importedMany", { count: result.imported_tests.length })}</b><p>{t("transfer.restored", { assets: result.asset_count, versions: result.version_count })}</p><Link className="link mt-2 inline-block" href="/admin/tests">{t("pages.overview.builderAction")}</Link></div> : null}
      {error ? <p role="alert" className="notice notice-error mt-4">{errorText}</p> : null}
    </section>

    <section className="panel p-6 lg:col-span-2" aria-label={t("transfer.packageContents")}>
      <div className="grid gap-6 sm:grid-cols-2"><div><h2 className="section-title">{t("transfer.included")}</h2><p>{t("transfer.contents")}</p></div><div><h2 className="section-title">{t("transfer.notIncluded")}</h2><p>{t("transfer.excluded")}</p></div></div>
    </section>
  </div>;
}
