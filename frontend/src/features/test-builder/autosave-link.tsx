"use client";

import Link, { type LinkProps } from "next/link";
import { useOptionalBuilderLifecycle } from "./builder-lifecycle";

export function AutosaveLink({ children, className, ...props }: LinkProps & { children: React.ReactNode; className?: string }) {
  const lifecycle = useOptionalBuilderLifecycle();
  const blocked = lifecycle?.transitioning || lifecycle?.deleting || lifecycle?.mutating;
  return <Link {...props} className={className} aria-disabled={blocked || undefined} onClick={(event) => {
    if (!lifecycle) return;
    event.preventDefault();
    if (blocked) return;
    void lifecycle.flushAutosaves().then((ready) => { if (ready) window.location.assign(String(props.href)); });
  }}>{children}</Link>;
}
