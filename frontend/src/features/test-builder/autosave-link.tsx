"use client";

import Link, { type LinkProps } from "next/link";
import { useOptionalBuilderLifecycle } from "./builder-lifecycle";

export function AutosaveLink({ children, className, ...props }: LinkProps & { children: React.ReactNode; className?: string }) {
  const lifecycle = useOptionalBuilderLifecycle();
  return <Link {...props} className={className} onClick={(event) => {
    if (!lifecycle) return;
    event.preventDefault();
    void lifecycle.flushAutosaves().then((ready) => { if (ready) window.location.assign(String(props.href)); });
  }}>{children}</Link>;
}
