import { Suspense } from "react";
import { AuthForm } from "@/features/auth/auth-form";

export default function LoginPage() {
  return <Suspense fallback={<p className="notice">Loading…</p>}><AuthForm mode="login" /></Suspense>;
}
