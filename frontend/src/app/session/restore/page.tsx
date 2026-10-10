import { UiText } from "@/lib/i18n/locale-provider";
import { Suspense } from "react";
import { SessionRestore } from "@/features/auth/session-restore";

export default function SessionRestorePage() {
  return <Suspense fallback={<p className="notice" role="status"><UiText message="auth.restoring" /></p>}><SessionRestore /></Suspense>;
}
