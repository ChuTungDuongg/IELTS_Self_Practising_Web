import { UiText } from "@/lib/i18n/locale-provider";
import { Suspense } from "react";
import { AuthForm } from "@/features/auth/auth-form";
import { AuthLayout } from "@/features/auth/auth-layout";

export default function RegisterPage() {
  return <AuthLayout><Suspense fallback={<p className="notice" role="status"><UiText message="common.loading" /></p>}><AuthForm mode="register" /></Suspense></AuthLayout>;
}
