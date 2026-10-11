"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon } from "@/components/ui/icons";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ApiError } from "@/lib/api/client";
import {
  createSpeakingModule, createSpeakingPart, createSpeakingPrompt, updateSpeakingPart,
  reorderSpeakingPrompts, deleteSpeakingPrompt,
  type BuilderModule, type BuilderSpeakingPart, type BuilderSpeakingPrompt, type BuilderVersion, type SpeakingPartUpdate,
} from "@/lib/api/builder";
import { useBuilderAutosave, useBuilderLifecycle } from "./builder-lifecycle";
import { SpeakingPromptEditor } from "./speaking-prompt-editor";

type PartDraft = Omit<SpeakingPartUpdate, "expected_revision">;
function content(part: BuilderSpeakingPart): PartDraft {
  return { title: part.title, instructions: part.instructions, prompts: [...part.prompts].sort((a, b) => a.order_index - b.order_index) };
}
function validDraft(draft: PartDraft) {
  return (draft.title?.length ?? 0) <= 240 && (draft.instructions?.length ?? 0) <= 4000 && draft.prompts.every(prompt =>
    prompt.prompt_text.length <= 20_000 && Number.isInteger(prompt.response_seconds) && prompt.response_seconds >= 1 && prompt.response_seconds <= 3600
    && Number.isInteger(prompt.preparation_seconds) && prompt.preparation_seconds >= (prompt.prompt_type === "LONG_TURN" ? 1 : 0) && prompt.preparation_seconds <= 3600
    && prompt.config_json.cue_points.length <= 12 && prompt.config_json.cue_points.every(point => point.length <= 1000));
}

function SpeakingPartEditor({ part, editable, focusTitle = false }: { part: BuilderSpeakingPart; editable: boolean; focusTitle?: boolean }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { flushAutosaves, runMutation, deleting, transitioning } = useBuilderLifecycle();
  const current = useRef(part);
  const savedContent = useRef(JSON.stringify(content(part)));
  const [draft, setDraft] = useState(() => content(part));
  const draftRef = useRef(draft);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);
  const cards = useRef<HTMLDivElement>(null);
  const positions = useRef(new Map<string, number>());
  const titleInput = useRef<HTMLInputElement>(null);
  useLayoutEffect(() => { if (focusTitle && editable) titleInput.current?.focus(); }, [editable, focusTitle]);
  useLayoutEffect(() => {
    draftRef.current = draft;
  }, [draft]);
  useLayoutEffect(() => {
    const next = new Map<string, number>();
    cards.current?.querySelectorAll<HTMLElement>("[data-prompt-id]").forEach(card => {
      const id = card.dataset.promptId!;
      const y = card.getBoundingClientRect().top;
      const previous = positions.current.get(id);
      if (previous !== undefined && previous !== y && card.animate && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
        card.animate([{ transform: `translateY(${previous - y}px)` }, { transform: "translateY(0)" }], { duration: 180, easing: "ease-out" });
      }
      next.set(id, y);
    });
    positions.current = next;
  }, [draft.prompts]);

  function changed(value: PartDraft) {
    draftRef.current = value;
    setDraft(value);
    stageValue(value, validDraft(value));
  }
  const { stageValue, markSaved } = useBuilderAutosave({
    resourceKey: `speaking-part:${part.id}`, value: draft, valid: validDraft(draft), enabled: editable && !busy && !conflict,
    save: async value => {
      try {
        const saved = await updateSpeakingPart(part.id, { ...value, expected_revision: current.current.revision });
        current.current = saved;
        savedContent.current = JSON.stringify(content(saved));
        setError(null);
        return saved;
      } catch (reason) {
        if (reason instanceof ApiError && reason.code === "DRAFT_REVISION_CONFLICT") setConflict(true);
        setError(reason instanceof ApiError ? reason.message : t("speaking.failed"));
        throw reason;
      }
    },
    onSaved: (saved, _submitted, unchanged) => {
      router.refresh();
      if (unchanged) {
        const canonical = content(saved);
        draftRef.current = canonical;
        setDraft(canonical);
        return canonical;
      }
    },
  });
  useLayoutEffect(() => {
    if (part.revision > current.current.revision && JSON.stringify(draftRef.current) === savedContent.current) {
      current.current = part;
      const canonical = content(part);
      savedContent.current = JSON.stringify(canonical);
      draftRef.current = canonical;
      setDraft(canonical);
      stageValue(canonical, validDraft(canonical));
      markSaved();
    }
  }, [markSaved, part, stageValue]);

  async function mutate(action: (latest: BuilderSpeakingPart) => Promise<BuilderSpeakingPart>, focusNew = false) {
    setError(null);
    try {
      // Flush before entering the shared mutation barrier, including other parts.
      if (!(await flushAutosaves())) return;
      setBusy(true);
      const previousIds = new Set(current.current.prompts.map(prompt => prompt.id));
      const saved = await runMutation(() => action(current.current));
      current.current = saved;
      const canonical = content(saved);
      savedContent.current = JSON.stringify(canonical);
      changed(canonical);
      markSaved();
      setFocusId(focusNew ? saved.prompts.find(prompt => !previousIds.has(prompt.id))?.id ?? null : null);
      router.refresh();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "DRAFT_REVISION_CONFLICT") setConflict(true);
      setError(reason instanceof ApiError ? reason.message : t("speaking.failed"));
    } finally { setBusy(false); }
  }
  function append(promptType: BuilderSpeakingPrompt["prompt_type"]) {
    void mutate(latest => createSpeakingPrompt(part.id, { expected_revision: latest.revision, prompt_type: promptType }), true);
  }
  function move(index: number, direction: -1 | 1) {
    const ids = draftRef.current.prompts.map(prompt => prompt.id);
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    void mutate(latest => reorderSpeakingPrompts(part.id, latest.revision, ids));
  }
  const main = draft.prompts.find(prompt => prompt.prompt_type === "LONG_TURN");
  return <fieldset className="speaking-part" disabled={!editable || busy || deleting || transitioning || conflict}>
    <legend>{t("speaking.part", { number: part.part_number })}</legend>
    <div className="speaking-part-details">
      <label className="field-label">{t("speaking.partTitle")}<input ref={titleInput} className="field mt-2" maxLength={240} value={draft.title ?? ""} onChange={event => changed({ ...draftRef.current, title: event.target.value || null })} /></label>
      <label className="field-label">{t("speaking.instructions")}<textarea className="field mt-2" rows={2} maxLength={4000} value={draft.instructions ?? ""} onChange={event => changed({ ...draftRef.current, instructions: event.target.value || null })} /></label>
    </div>
    <p className="section-description">{t("speaking.timerHelp")}</p>
    <div className="speaking-prompt-sequence" ref={cards}>
      {draft.prompts.map((prompt, index) => <SpeakingPromptEditor key={prompt.id} prompt={prompt} number={index + 1} focus={focusId === prompt.id}
        canMoveUp={index > 0 && (prompt.prompt_type === "LONG_TURN" || draft.prompts[index - 1].prompt_type !== "LONG_TURN")} canMoveDown={index < draft.prompts.length - 1 && prompt.prompt_type !== "LONG_TURN"}
        onChange={change => changed({ ...draftRef.current, prompts: draftRef.current.prompts.map(item => item.id === prompt.id ? { ...item, ...change } : item) })}
        onMove={direction => move(index, direction)} onDelete={() => void mutate(latest => deleteSpeakingPrompt(part.id, prompt.id, latest.revision))} />)}
      {!draft.prompts.length ? <p className="section-description">{t("speaking.empty")}</p> : null}
    </div>
    {part.part_number === 2 && !main ? <button type="button" className="btn mt-4" onClick={() => append("LONG_TURN")}><PlusIcon className="size-4" />{t("speaking.addLongTurn")}</button> : null}
    <button type="button" className="btn btn-ghost mt-4" disabled={draft.prompts.length >= 100} onClick={() => append(part.part_number === 2 ? "FOLLOW_UP" : "SHORT_ANSWER")}><PlusIcon className="size-4" />{t(part.part_number === 2 ? "speaking.addFollowup" : "speaking.addQuestion")}</button>
    {part.part_number === 2 ? <section className="speaking-candidate-preview" aria-label={t("speaking.preview")}>
      <h3>{t("speaking.preview")}</h3>
      <p className="speaking-authored-text">{main?.prompt_text || t("speaking.previewEmpty")}</p>
      {main?.config_json.cue_points.length ? <><p>{t("speaking.youShouldSay")}</p><ul>{main.config_json.cue_points.map((point, index) => <li key={index}>{point}</li>)}</ul></> : null}
    </section> : null}
    {error ? <p className="notice notice-error mt-4" role="alert">{error}</p> : null}
  </fieldset>;
}

export function SpeakingBuilder({ version, editable = true }: { version: BuilderVersion; editable?: boolean }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { runMutation, flushAutosaves, deleting, transitioning, mutating } = useBuilderLifecycle();
  const initial = version.modules.find(module => module.module_type === "SPEAKING");
  const [created, setCreated] = useState<BuilderModule | null>(null);
  const speakingModule = initial ?? created;
  const [newParts, setNewParts] = useState<BuilderSpeakingPart[]>([]);
  const [focusPartId, setFocusPartId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mutable = editable && version.status === "DRAFT";
  const disabled = !mutable || deleting || transitioning || mutating;
  async function create() {
    try {
      if (!(await flushAutosaves())) return;
      const saved = await runMutation(() => createSpeakingModule(version.id));
      setCreated(saved);
      setFocusPartId(saved.speaking_parts?.find(part => part.part_number === 1)?.id ?? null);
      router.refresh();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t("speaking.failed")); }
  }
  async function createPart(number: 1 | 2 | 3) {
    if (!speakingModule) return;
    try {
      if (!(await flushAutosaves())) return;
      const saved = await runMutation(() => createSpeakingPart(speakingModule.id, number));
      setNewParts(parts => [...parts.filter(part => part.id !== saved.id), saved]);
      setFocusPartId(saved.id);
      router.refresh();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : t("speaking.failed")); }
  }
  if (!speakingModule) return <section className="reading-empty speaking-empty">
    <h2>{t("speaking.build")}</h2><p>{t("speaking.createHelp")}</p>
    <button className="btn mt-5" disabled={disabled} onClick={() => void create()}><PlusIcon className="size-4" />{t("speaking.create")}</button>
    {error ? <p className="notice notice-error mt-4" role="alert">{error}</p> : null}
  </section>;
  const parts = [...(speakingModule.speaking_parts ?? []), ...newParts.filter(part => !speakingModule.speaking_parts?.some(item => item.id === part.id))];
  return <section className="speaking-builder">
    {!mutable ? <p className="notice">{t("builder.frozen")}</p> : null}
    {([1, 2, 3] as const).map(number => {
      const part = parts.find(item => item.part_number === number);
      return part ? <SpeakingPartEditor key={part.id} part={part} editable={mutable} focusTitle={focusPartId === part.id} />
        : <div key={number} className="speaking-part"><button className="btn" disabled={disabled} onClick={() => void createPart(number)}>{t("speaking.createPart", { number })}</button></div>;
    })}
    {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
  </section>;
}
