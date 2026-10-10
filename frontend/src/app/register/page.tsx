import { UiText } from "@/lib/i18n/locale-provider";
import { Suspense } from "react";
import { AuthForm } from "@/features/auth/auth-form";

export default function RegisterPage() {
  return <Suspense fallback={<p className="notice"><UiText message="common.loading" /></p>}><AuthForm mode="register" /></Suspense>;
}
