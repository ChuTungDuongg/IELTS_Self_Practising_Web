"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { googleLoginUrl, login, register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "./auth-provider";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { confirmSession } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const next = searchParams.get("next");
      router.push(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Authentication could not be completed.");
    } finally {
      setPending(false);
    }
  }

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
