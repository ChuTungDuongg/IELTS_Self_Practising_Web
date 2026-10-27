"use client";
import { useEffect, useRef, useState } from "react";
import type { ClassroomResource, ClassroomSection } from "@/lib/api/classroom-content";
import { PostComposer } from "../post-composer";
import { ResourceEditor } from "../resource-editor";
import { useContentTranslation } from "../content-messages";
import { StreamAvatar, StreamGlyph } from "./identity";
import { useStreamText } from "./messages";

export function StreamComposer({ classroomId, resources, sections, name, initialCompose, request = 0, onDone, onResourceDone }: { classroomId: string; resources: ClassroomResource[]; sections: ClassroomSection[]; name?: string; initialCompose: boolean; request?: number; onDone: () => Promise<unknown>; onResourceDone: () => Promise<unknown> }) {
  const { tt } = useStreamText(), { ct } = useContentTranslation();
  const [editor, setEditor] = useState<"ANNOUNCEMENT" | "DISCUSSION" | "FILE" | "LINK" | null>(initialCompose ? "ANNOUNCEMENT" : null);
  const trigger = useRef<HTMLButtonElement>(null), root = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!request) return;
    let focusFrame: number | undefined;
    const frame = requestAnimationFrame(() => { setEditor("ANNOUNCEMENT"); focusFrame = requestAnimationFrame(() => { root.current?.scrollIntoView?.({ block: "nearest" }); root.current?.querySelector<HTMLElement>("input, textarea")?.focus({ preventScroll: true }); }); });
    return () => { cancelAnimationFrame(frame); if (focusFrame !== undefined) cancelAnimationFrame(focusFrame); };
  }, [request]);
  function close() { setEditor(null); requestAnimationFrame(() => trigger.current?.focus()); }
  return <section ref={root} className="stream-compose" aria-label={ct("newPost")}>
    {editor ? editor === "FILE" || editor === "LINK" ? <ResourceEditor key={editor} initialKind={editor} classroomId={classroomId} sections={sections} onDone={async () => { await onResourceDone(); close(); }} onCancel={close} /> : <PostComposer key={editor} initialKind={editor} classroomId={classroomId} resources={resources} onCancel={close} onDone={async () => { await onDone(); close(); }} /> : <>
      <div className="stream-compose-prompt"><StreamAvatar name={name} /><button ref={trigger} className="stream-compose-trigger" type="button" aria-label={tt("compose")} onClick={() => setEditor("ANNOUNCEMENT")}>{tt("share")}</button></div>
      <div className="stream-compose-actions">{([ ["ANNOUNCEMENT", "announcement"], ["FILE", "resource"], ["LINK", "link"], ["DISCUSSION", "discussion"] ] as const).map(([kind, label]) => <button key={kind} type="button" className="stream-compose-chip" data-kind={kind} onClick={() => setEditor(kind)}><StreamGlyph kind={kind} />{tt(label)}</button>)}<button type="button" className="btn btn-primary stream-compose-publish" aria-label={ct("newPost")} onClick={() => setEditor("ANNOUNCEMENT")}><StreamGlyph kind="SEND" />{ct("publish")}</button></div>
    </>}
  </section>;
}
