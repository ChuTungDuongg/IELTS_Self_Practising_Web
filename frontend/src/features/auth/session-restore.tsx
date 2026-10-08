"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getCurrentUser } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { authRedirectPath, safeAuthDestination } from "@/lib/auth-destination";

export function SessionRestore() {
  const searchParams = useSearchParams();
  const destination = safeAuthDestination(searchParams.get("next"));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    // Always check cookies, even if a persistent AppShell still holds a previous user.
    getCurrentUser()
      .then(() => {
        if (active) window.location.replace(destination);
      })
      .catch((caught) => {
        if (!active) return;
        if (caught instanceof ApiError && (caught.status === 401 || caught.code === "ACCOUNT_INACTIVE")) {
          window.location.replace(authRedirectPath("/login", destination));
        } else {
          setError(caught instanceof Error ? caught.message : "The session could not be restored.");
        }
      });
    return () => { active = false; };
  }, [destination]);

  if (error) return <p className="notice" role="alert">{error}</p>;
  return <p className="notice" role="status">Đang khôi phục phiên đăng nhập…</p>;
}
