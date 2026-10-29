"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";
import { useGravityMotion } from "./gravity-motion-provider";

export function GravityMotionControls() {
  const { t } = useTranslation();
  const motion = useGravityMotion();
  const state = motion?.state ?? "unavailable";
  const paused = motion?.paused ?? false;
  const unavailable = state === "unavailable" || state === "static";
  return <div className="gravity-motion-controls" role="group" aria-label={t("gravity.motionControls")} data-scene={state}>
    <p className="gravity-motion-label">{t("gravity.motionControls")}</p>
    <div className="gravity-motion-buttons">
      <button type="button" className="gravity-control" disabled={unavailable} aria-pressed={paused} onClick={state === "failed" ? motion?.retry : motion?.togglePause}>
        {t(state === "failed" ? "gravity.retry" : paused ? "gravity.play" : "gravity.pause")}
      </button>
      <button type="button" className="gravity-control" disabled={state !== "ready" || paused} onClick={motion?.scatter}>{t("gravity.scatter")}</button>
    </div>
    <p className="gravity-scene-note" role="status">{t(state === "static" ? "gravity.preparing" : state === "failed" || state === "unavailable" ? "gravity.unavailable" : paused ? "gravity.pausedStatus" : "gravity.readyStatus")}</p>
  </div>;
}
