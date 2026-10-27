"use client";
import type { ReactNode } from "react";
import type { ClassroomPost } from "@/lib/api/classroom-content";
import { ReadingIcon } from "@/components/ui/icons";
import { formatProjectDateTime } from "@/lib/date-time";
import { useContentTranslation } from "../content-messages";

export function StreamAvatar({ name = "" }: { name?: string }) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = [words[0], words.length > 1 ? words[words.length - 1] : undefined].filter(Boolean).map(word => Array.from(word!)[0]).join("").toLocaleUpperCase();
  return <span className="stream-avatar" aria-hidden="true">{letters || "?"}</span>;
}
export function StreamTime({ value }: { value: string }) {
  const date = new Date(value);
  return Number.isFinite(date.valueOf()) ? <time dateTime={value}>{formatProjectDateTime(value)}</time> : null;
}
export function StreamGlyph({ kind }: { kind: string }) {
  const paths: Record<string, ReactNode> = {
    ANNOUNCEMENT: <><path d="m4 10 14-6v16L4 14ZM4 10v4M7 15l2 6h3l-2-5" /></>,
    DISCUSSION: <path d="M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0Z" />,
    LINK: <><path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" /></>,
    PEOPLE: <><circle cx="9" cy="7" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3" /></>,
    PIN: <path d="m9 3 12 12-4 1-4 5-1-6-5-5ZM3 21l6-6" />,
    SEND: <path d="m3 3 19 8-8 3-3 8ZM3 3l11 11" />,
  };
  return paths[kind] ? <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[kind]}</svg> : <ReadingIcon />;
}
export function StreamBadge({ post }: { post: ClassroomPost }) {
  const { ct } = useContentTranslation();
  return <span className="stream-kind" data-kind={post.kind}><StreamGlyph kind={post.kind} />{ct(post.kind === "ANNOUNCEMENT" ? "announcement" : post.kind === "DISCUSSION" ? "discussion" : post.kind === "ASSIGNMENT_ACTIVITY" ? "assignmentActivity" : "resourceActivity")}</span>;
}
