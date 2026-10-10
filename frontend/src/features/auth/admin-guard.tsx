"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./auth-provider";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const { user, loading, sessionError } = useAuth();
  const router = useRouter();
  const pathname = usePathname() ?? "/admin";

  useEffect(() => {
    if (!loading && !user && !sessionError) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [loading, pathname, router, sessionError, user]);

  if (sessionError) return <p role="alert" className="notice">{sessionError}</p>;
  if (loading || !user) return <p className="notice">{t("admin.checking")}</p>;
  if (user.role !== "ADMIN") {
    return <section className="empty-state"><h1>{t("admin.forbidden")}</h1><p>{t("admin.only")}</p></section>;
  }
  return children;
}
