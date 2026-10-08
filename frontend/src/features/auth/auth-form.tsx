"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { googleLoginUrl, login, register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { safeAuthDestination } from "@/lib/auth-destination";
import { useAuth } from "./auth-provider";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const searchParams = useSearchParams();
  const { user, loading, sessionError, confirmSession } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      setError("Passwords do not match.");
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
      setError(caught instanceof ApiError ? caught.message : "Authentication could not be completed.");
    } finally {
      setPending(false);
    }
  }

  if (loading || user) return <p className="notice" role="status">Checking your session…</p>;
  if (sessionError) return <p role="alert" className="notice">{sessionError}</p>;

  return <section className="auth-card">
    <div><p className="page-eyebrow">IELTS Studio account</p><h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1><p>{mode === "login" ? "Sign in to continue your practice." : "Keep your attempts, History, and Analytics private to you."}</p></div>
    <form onSubmit={submit} className="auth-form">
      {mode === "register" ? <label>Name<input name="display_name" required minLength={1} maxLength={160} autoComplete="name" /></label> : null}
      <label>Email<input name="email" type="email" required autoComplete="email" /></label>
      <label>Password<input name="password" type="password" required minLength={mode === "register" ? 8 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
      {mode === "register" ? <label>Confirm password<input name="confirm_password" type="password" required minLength={8} autoComplete="new-password" /></label> : null}
      {error ? <p role="alert" className="notice">{error}</p> : null}
      <button type="submit" className="btn btn-primary" disabled={pending}>{pending ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
    </form>
    <a className="btn btn-secondary" href={googleLoginUrl}>Continue with Google</a>
    <p>{mode === "login" ? <>New here? <Link href="/register">Create an account</Link></> : <>Already registered? <Link href="/login">Login</Link></>}</p>
  </section>;
}
