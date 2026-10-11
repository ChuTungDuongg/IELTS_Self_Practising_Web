"use client";

import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { BuilderSpeakingPrompt } from "@/lib/api/builder";

export function SpeakingPromptEditor({ prompt, number, canMoveUp, canMoveDown, focus, onChange, onMove, onDelete }: {
  prompt: BuilderSpeakingPrompt; number: number; canMoveUp: boolean; canMoveDown: boolean; focus: boolean;
  onChange: (change: Partial<BuilderSpeakingPrompt>) => void;
  onMove: (direction: -1 | 1) => void; onDelete: () => void;
}) {
  const { t } = useTranslation();
  const input = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => { if (focus) input.current?.focus(); }, [focus]);
  const longTurn = prompt.prompt_type === "LONG_TURN";
  const responseValid = Number.isInteger(prompt.response_seconds) && prompt.response_seconds >= 1 && prompt.response_seconds <= 3600;
  const preparationValid = Number.isInteger(prompt.preparation_seconds) && prompt.preparation_seconds >= 1 && prompt.preparation_seconds <= 3600;
  const label = longTurn ? t("speaking.cuePrompt") : t("speaking.promptNumber", { number });
  return <article className={`speaking-prompt-card${longTurn ? " speaking-cue-card" : ""}`} data-prompt-id={prompt.id}>
    <label className="field-label" htmlFor={`speaking-prompt-${prompt.id}`}>{label}</label>
    <textarea ref={input} id={`speaking-prompt-${prompt.id}`} className="field mt-2" rows={longTurn ? 4 : 2} maxLength={20_000} value={prompt.prompt_text} onChange={event => onChange({ prompt_text: event.target.value })} />
    {longTurn ? <div className="mt-4">
      <label className="field-label" htmlFor={`speaking-cues-${prompt.id}`}>{t("speaking.cuePoints")}</label>
      <textarea id={`speaking-cues-${prompt.id}`} className="field mt-2" rows={4} aria-describedby={`speaking-cue-help-${prompt.id}`} value={prompt.config_json.cue_points.join("\n")} onChange={event => onChange({ config_json: { cue_points: event.target.value === "" ? [] : event.target.value.split(/\r?\n/) } })} />
      <p className="section-description" id={`speaking-cue-help-${prompt.id}`}>{t("speaking.cueHelp")}</p>
    </div> : null}
    <div className="speaking-timers">
      {longTurn ? <label className="field-label">{t("speaking.preparation")}
        <input className="field mt-2" type="number" min={1} max={3600} aria-invalid={!preparationValid} value={prompt.preparation_seconds} onChange={event => onChange({ preparation_seconds: Number(event.target.value) })} />
      </label> : null}
      <label className="field-label">{t("speaking.response")}
        <input className="field mt-2" type="number" min={1} max={3600} aria-invalid={!responseValid} value={prompt.response_seconds} onChange={event => onChange({ response_seconds: Number(event.target.value) })} />
      </label>
    </div>
    {!responseValid || (longTurn && !preparationValid) ? <p className="notice notice-error mt-2" role="alert">{t("speaking.timerInvalid")}</p> : null}
    <div className="speaking-card-actions">
      <button className="btn btn-ghost" type="button" disabled={!canMoveUp} onClick={() => onMove(-1)}>{t("speaking.up")}</button>
      <button className="btn btn-ghost" type="button" disabled={!canMoveDown} onClick={() => onMove(1)}>{t("speaking.down")}</button>
      <button className="btn btn-ghost" type="button" onClick={onDelete}>{t("speaking.delete")}</button>
    </div>
  </article>;
}
