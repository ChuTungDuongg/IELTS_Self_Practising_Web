"use client";

import { useEffect, useRef, useState } from "react";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { googleLoginUrl, login, register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { safeAuthDestination } from "@/lib/auth-destination";
import { useAuth } from "./auth-provider";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const { user, loading, sessionError, confirmSession } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: TranslationKey } | null>(null);
  const navigating = useRef(false);
  const destination = safeAuthDestination(searchParams.get("next"));

  useEffect(() => {
    if (!loading && user && !pending && !navigating.current) {
      navigating.current = true;
      window.location.replace(destination);
    }
  }, [destination, loading, pending, user]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    if (mode === "register" && data.get("password") !== data.get("confirm_password")) {
      setError({ message: "auth.passwordMismatch" });
      setPending(false);
      return;
    }
    try {
      if (mode === "login") {
        await login({ email: String(data.get("email") ?? ""), password: String(data.get("password") ?? "") });
      } else {
        await register({
          email: String(data.get("email") ?? ""),
          display_name: String(data.get("display_name") ?? ""),
          password: String(data.get("password") ?? ""),
        });
      }
      await confirmSession();
      navigating.current = true;
      // A document request uses the confirmed cookies without stale prefetched RSC data.
      window.location.replace(destination);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "auth.failed" });
    } finally {
      setPending(false);
    }
  }

  if (loading || user) return <p className="notice" role="status">{t("auth.checking")}</p>;
  if (sessionError) return <p role="alert" className="notice">{sessionError}</p>;

  return <section className="auth-card">
    <div><p className="page-eyebrow">{t("auth.account")}</p><h1>{mode === "login" ? t("auth.welcome") : t("auth.createTitle")}</h1><p>{mode === "login" ? t("auth.signInDescription") : t("auth.registerDescription")}</p></div>
    <form onSubmit={submit} className="auth-form">
      {mode === "register" ? <label>{t("auth.name")}<input name="display_name" required minLength={1} maxLength={160} autoComplete="name" /></label> : null}
      <label>{t("auth.email")}<input name="email" type="email" required autoComplete="email" /></label>
      <label>{t("auth.password")}<input name="password" type="password" required minLength={mode === "register" ? 8 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
      {mode === "register" ? <label>{t("auth.confirmPassword")}<input name="confirm_password" type="password" required minLength={8} autoComplete="new-password" /></label> : null}
      {error ? <p role="alert" className="notice">{typeof error === "string" ? error : error ? t(error.message) : null}</p> : null}
      <button type="submit" className="btn btn-primary" disabled={pending}>{pending ? t("auth.wait") : mode === "login" ? t("auth.signIn") : t("auth.create")}</button>
    </form>
    <a className="btn btn-secondary" href={googleLoginUrl}>{t("auth.google")}</a>
    <p>{mode === "login" ? <>{t("auth.newHere")} <Link href="/register">{t("auth.createLink")}</Link></> : <>{t("auth.registered")} <Link href="/login">{t("shell.login")}</Link></>}</p>
  </section>;
}
