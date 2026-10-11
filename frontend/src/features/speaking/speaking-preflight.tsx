"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { SpeakingRecorder } from "./speaking-recorder";

export function SpeakingPreflight({ onReady }: { onReady(recorder: SpeakingRecorder): void | Promise<void> }) {
  const { t } = useTranslation();
  const recorder = useRef<SpeakingRecorder | null>(null);
  const handedOff = useRef(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [level, setLevel] = useState(0);
  const [signal, setSignal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mime, setMime] = useState("");
  const [error, setError] = useState<"unsupported" | "permission" | null>(null);
  useEffect(() => () => { if (!handedOff.current) recorder.current?.close(); }, []);
  async function check(deviceId?: string) {
    setError(null); setBusy(true); setSignal(false); setMime("");
    recorder.current?.close();
    const next = new SpeakingRecorder();
    next.onLevel = (value) => { setLevel(value); if (value > .015) setSignal(true); };
    recorder.current = next;
    try {
      await next.prepare(deviceId); setMime(next.mimeType);
      const inputs = await navigator.mediaDevices.enumerateDevices?.().catch(() => []) ?? [];
      setDevices(inputs.filter((device) => device.kind === "audioinput"));
    } catch (caught) { setError(caught instanceof Error && caught.message === "MICROPHONE_UNSUPPORTED" ? "unsupported" : "permission"); }
    finally { setBusy(false); }
  }
  return <section className="speaking-card" aria-labelledby="mic-heading">
    <h2 id="mic-heading">{t("speakingRuntime.setup")}</h2>
    <p>{t("speakingRuntime.micHint")}</p>
    <button className="btn btn-secondary" disabled={busy} onClick={() => void check()}>{t("speakingRuntime.check")}</button>
    {mime ? <><label className="field-label">{t("speakingRuntime.input")}<select onChange={(event) => void check(event.target.value)} disabled={busy}>{devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `${t("speakingRuntime.input")} ${index + 1}`}</option>)}</select></label>
      <meter aria-label={t("speakingRuntime.level")} min={0} max={1} value={level} aria-valuenow={level} />
      <p>{mime}</p><p role="status">{t(signal ? "speakingRuntime.ready" : "speakingRuntime.silent")}</p>
      <button className="btn btn-primary" disabled={!signal || busy} onClick={() => { handedOff.current = true; void onReady(recorder.current!); }}>{t("speakingRuntime.start")}</button></> : null}
    {error ? <p role="alert" className="notice notice-error">{t(error === "unsupported" ? "speakingRuntime.unsupported" : "speakingRuntime.permission")}</p> : null}
  </section>;
}
