"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { googleLoginUrl, login, register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { safeAuthDestination } from "@/lib/auth-destination";
import { AppLogo } from "@/components/ui/app-logo";
import { useAuth } from "./auth-provider";
import { AuthIcon, GoogleIcon } from "./auth-icons";
import { PasswordField } from "./password-field";
import styles from "./auth.module.css";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const { user, loading, sessionError, confirmSession } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: TranslationKey } | null>(null);
  const navigating = useRef(false);
  const submitting = useRef(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const id = useId();
  const errorId = `${id}-error`;
  const passwordMismatch = typeof error === "object" && error?.message === "auth.passwordMismatch";
  const destination = safeAuthDestination(searchParams.get("next"));

  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  useEffect(() => {
    if (!loading && user && !pending && !navigating.current) {
      navigating.current = true;
      window.location.replace(destination);
    }
  }, [destination, loading, pending, user]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || navigating.current) return;
    submitting.current = true;
    const data = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    if (mode === "register" && data.get("password") !== data.get("confirm_password")) {
      setError({ message: "auth.passwordMismatch" });
      setPending(false);
      submitting.current = false;
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
      submitting.current = false;
    }
  }

  if (loading || user) return <p className="notice" role="status">{t("auth.checking")}</p>;
  if (sessionError) return <p role="alert" className="notice">{sessionError}</p>;

  return <section className={styles.card} aria-labelledby={`${id}-title`}>
    <div className={styles.cardBrand}><AppLogo variant="primary" /><strong>BandPilot</strong></div>
    <div className={styles.cardHeading}>
      <p className="sr-only">{t("auth.account")}</p>
      <h1 id={`${id}-title`}>{mode === "login" ? t("auth.welcome") : t("auth.createTitle")}</h1>
      <p>{mode === "login" ? t("auth.signInDescription") : t("auth.registerDescription")}</p>
    </div>
    <form onSubmit={submit} className={styles.form} aria-label={t("auth.account")} aria-busy={pending} aria-describedby={error ? errorId : undefined}>
      {mode === "register" ? <div className={styles.field}>
        <label htmlFor={`${id}-name`}>{t("auth.name")}</label>
        <div className={styles.inputWrap}><AuthIcon name="person" className={styles.leadingIcon} /><input id={`${id}-name`} name="display_name" required minLength={1} maxLength={160} autoComplete="name" /></div>
      </div> : null}
      <div className={styles.field}>
        <label htmlFor={`${id}-email`}>{t("auth.email")}</label>
        <div className={styles.inputWrap}><AuthIcon name="email" className={styles.leadingIcon} /><input id={`${id}-email`} name="email" type="email" required autoComplete="email" autoCapitalize="none" spellCheck={false} /></div>
      </div>
      <PasswordField name="password" label={t("auth.password")} minLength={mode === "register" ? 8 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} hint={mode === "register" ? t("gravity.passwordHint") : undefined} invalid={passwordMismatch} errorId={errorId} />
      {mode === "register" ? <PasswordField name="confirm_password" label={t("auth.confirmPassword")} minLength={8} autoComplete="new-password" invalid={passwordMismatch} errorId={errorId} /> : null}
      {error ? <p id={errorId} ref={errorRef} role="alert" tabIndex={-1} className={styles.error}>{typeof error === "string" ? error : t(error.message)}</p> : null}
      <button type="submit" className={styles.submit} disabled={pending}>
        <span>{pending ? t("auth.wait") : mode === "login" ? t("auth.signIn") : t("auth.create")}</span>
        <AuthIcon name={pending ? "clock" : "arrow"} />
      </button>
    </form>
    <div className={styles.separator}><span>{t("auth.or")}</span></div>
    <a className={styles.google} href={googleLoginUrl}><GoogleIcon /><span>{t("auth.google")}</span></a>
    <p className={styles.switchMode}>{mode === "login" ? <>{t("auth.newHere")} <Link href="/register">{t("auth.createLink")}</Link></> : <>{t("auth.registered")} <Link href="/login">{t("shell.login")}</Link></>}</p>
  </section>;
}
