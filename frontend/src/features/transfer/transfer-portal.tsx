"use client";

import { useState } from "react";
import Link from "next/link";
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
  const [selected, setSelected] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<TransferImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      setError(reason instanceof ApiError ? reason.message : "The test package could not be exported.");
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
      setError(reason instanceof ApiError ? reason.message : "The test package could not be imported.");
    } finally {
      setImporting(false);
    }
  }

  return <div className="grid gap-6 lg:grid-cols-2">
    <section className="panel p-6" aria-labelledby="transfer-export-title">
      <p className="page-eyebrow">Machine A</p>
      <h2 id="transfer-export-title" className="section-title">Export authored tests</h2>
      <p className="section-description">Select one or more tests. Every version and its referenced images and audio will be packaged.</p>
      <div className="mt-5 grid gap-3">
        {tests.map((test) => <label key={test.id} className="question-group-card cursor-pointer">
          <input type="checkbox" checked={selected.includes(test.id)} onChange={() => toggle(test.id)} aria-label={`Select ${test.title}`} />
          <span className="min-w-0 flex-1"><b className="block">{test.title}</b><small className="text-[var(--muted)]">{test.latestVersion ? `Latest V${test.latestVersion}` : "No versions"} · {test.states.join(" / ") || "No state"} · {test.skills.join(", ") || "No modules"}{test.archived ? " · Archived test" : ""}</small></span>
        </label>)}
        {!tests.length ? <p className="notice">No authored tests are available.</p> : null}
      </div>
      <button type="button" className="btn btn-primary mt-5" disabled={!selected.length || exporting} onClick={() => void download()}>{exporting ? "Exporting…" : "Export selected"}</button>
    </section>

    <section className="panel p-6" aria-labelledby="transfer-import-title">
      <p className="page-eyebrow">Machine B</p>
      <h2 id="transfer-import-title" className="section-title">Import test package</h2>
      <p className="section-description">This imports authored tests and attached media. Practice attempts and history are not included.</p>
      <label className="field-label mt-5 block">Choose ZIP<input aria-label="Test package ZIP" className="field mt-2" type="file" accept=".zip,application/zip" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setResult(null); setError(null); }} /></label>
      <p className="mt-3 text-sm text-[var(--muted)]">Selected: {file?.name ?? "None"}</p>
      <button type="button" className="btn btn-primary mt-5" disabled={!file || importing} onClick={() => void upload()}>{importing ? "Importing…" : "Import"}</button>
      {result ? <div role="status" className="notice notice-success mt-4"><b>Imported {result.imported_tests.length} test{result.imported_tests.length === 1 ? "" : "s"}</b><p>{result.asset_count} assets restored · {result.version_count} versions</p><Link className="link mt-2 inline-block" href="/admin/tests">Open Builder</Link></div> : null}
      {error ? <p role="alert" className="notice notice-error mt-4">{error}</p> : null}
    </section>

    <section className="panel p-6 lg:col-span-2" aria-label="Transfer package contents">
      <div className="grid gap-6 sm:grid-cols-2"><div><h2 className="section-title">Included</h2><p>Tests, versions, questions, images, audio</p></div><div><h2 className="section-title">Not included</h2><p>Attempts, scores, history, analytics</p></div></div>
    </section>
  </div>;
}
