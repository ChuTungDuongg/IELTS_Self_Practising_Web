"use client";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { useLmsText } from "./messages";

export function useLmsData<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: unknown }>({ data: null, loading: true, error: null });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      setState({ data: null, loading: true, error: null });
      try { const data = await load(controller.signal); if (!controller.signal.aborted) setState({ data, loading: false, error: null }); }
      catch (error) { if (!controller.signal.aborted) setState({ data: null, loading: false, error }); }
    });
    return () => controller.abort();
  }, [load, revision]);
  return { ...state, refresh: () => setRevision(value => value + 1) };
}
export function LmsLoadState({ loading, error, retry }: { loading: boolean; error: unknown; retry: () => void }) { const { lt } = useLmsText(); return loading ? <p role="status">{lt("loading")}</p> : error ? <div><p role="alert">{error instanceof ApiError ? error.message : lt("error")}</p><button className="btn btn-secondary" onClick={retry}>{lt("retry")}</button></div> : null; }
