"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";
import { useGravityMotion } from "./gravity-motion-provider";
import { FooterIcon } from "@/components/ui/footer-icon";

export function GravityMotionControls() {
  const { t } = useTranslation();
  const motion = useGravityMotion();
  const state = motion?.state ?? "unavailable";
  const paused = motion?.paused ?? false;
  const unavailable = state === "unavailable" || state === "static";
  return <div className="gravity-motion-controls" role="group" aria-label={t("gravity.motionControls")} data-scene={state}>
    <p className="gravity-motion-label"><FooterIcon name="orbit" />{t("gravity.motionControls")}</p>
    <div className="gravity-motion-buttons">
      <button type="button" className="gravity-control" disabled={unavailable} aria-pressed={paused} onClick={state === "failed" ? motion?.retry : motion?.togglePause}>
        <FooterIcon name={state === "failed" ? "scatter" : paused ? "play" : "pause"} />
        {t(state === "failed" ? "gravity.retry" : paused ? "gravity.play" : "gravity.pause")}
      </button>
      <button type="button" className="gravity-control" disabled={state !== "ready" || paused} onClick={motion?.scatter}><FooterIcon name="scatter" />{t("gravity.scatter")}</button>
    </div>
    <p className="gravity-scene-note" role="status"><FooterIcon name="info" />{t(state === "static" ? "gravity.preparing" : state === "failed" || state === "unavailable" ? "gravity.unavailable" : paused ? "gravity.pausedStatus" : "gravity.readyStatus")}</p>
  </div>;
}
