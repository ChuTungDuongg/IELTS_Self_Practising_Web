"use client";


import Link from "next/link";
import { GOVERNANCE_PAGE_SIZE } from "@/lib/api/pagination";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function PageNavigation({ path, offset, hasNext }: { path: string; offset: number; hasNext: boolean; }) {
  const { t } = useTranslation();
  const href = (nextOffset: number) => {
    const [pathname, query] = path.split("?");
    const params = new URLSearchParams(query);
    params.set("offset", String(nextOffset));
    return `${pathname}?${params}`;
  };
  return <nav className="flex gap-3 mt-5" aria-label={t("pagination.label")}>
    {offset > 0 ? <Link className="btn btn-secondary" href={href(Math.max(0, offset - GOVERNANCE_PAGE_SIZE))}>{t("pagination.previous")}</Link> : null}
    {hasNext ? <Link className="btn btn-secondary" href={href(offset + GOVERNANCE_PAGE_SIZE)}>{t("pagination.next")}</Link> : null}
  </nav>;
}
