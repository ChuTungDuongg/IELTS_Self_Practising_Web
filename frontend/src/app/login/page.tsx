import { UiText } from "@/lib/i18n/locale-provider";
import { Suspense } from "react";
import { AuthForm } from "@/features/auth/auth-form";

export default function LoginPage() {
  return <Suspense fallback={<p className="notice"><UiText message="common.loading" /></p>}><AuthForm mode="login" /></Suspense>;
}
