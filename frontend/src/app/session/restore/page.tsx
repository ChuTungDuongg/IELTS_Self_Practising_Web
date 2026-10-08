import { Suspense } from "react";
import { SessionRestore } from "@/features/auth/session-restore";

export default function SessionRestorePage() {
  return <Suspense fallback={<p className="notice" role="status">Đang khôi phục phiên đăng nhập…</p>}><SessionRestore /></Suspense>;
}
